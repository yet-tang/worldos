from __future__ import annotations

import hmac
import os
from pathlib import Path
from typing import Any

import httpx
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from pydantic import AnyHttpUrl

from .agent_services import WorldReadService


READ_SCOPE = "world:read"
WRITE_SCOPE = "world:write"


class StaticMCPTokenVerifier(TokenVerifier):
    async def verify_token(self, token: str) -> AccessToken | None:
        configured = os.environ.get("WORLDOS_MCP_TOKEN", "").strip()
        if not configured or len(configured) < 32:
            return None
        if not hmac.compare_digest(configured, token):
            return None
        return AccessToken(token=token, client_id="worldos-agent", scopes=[READ_SCOPE, WRITE_SCOPE])


def _database_path() -> Path:
    return Path(os.environ.get("WORLDOS_DB", "/data/world.db"))


def _service() -> WorldReadService:
    return WorldReadService(_database_path())


def _control_base_url() -> str:
    return os.environ.get("WORLDOS_CONTROL_INTERNAL_URL", "http://inspector:8765/api/control").rstrip("/")


def _control_token() -> str:
    token = os.environ.get("WORLDOS_CONTROL_TOKEN", "").strip()
    if len(token) < 32:
        raise RuntimeError("WORLDOS_CONTROL_TOKEN is not configured for MCP write tools")
    return token


def _control_request(
    method: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
    if_match: str | None = None,
) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {_control_token()}"}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    if if_match:
        headers["If-Match"] = if_match
    with httpx.Client(timeout=120.0) as client:
        response = client.request(method, _control_base_url() + path, json=payload, headers=headers)
    try:
        body = response.json()
    except ValueError:
        body = {"error": response.text}
    if response.status_code >= 400:
        raise RuntimeError(f"WorldOS Control API {response.status_code}: {body.get('error', body)}")
    if isinstance(body, dict):
        body["http_status"] = response.status_code
        body["idempotency_replayed"] = response.headers.get("Idempotency-Replayed", "").lower() == "true"
    return body


def build_mcp() -> FastMCP:
    public_url = os.environ.get("WORLDOS_MCP_PUBLIC_URL", "https://worldos.invalid/mcp").strip()
    issuer_url = os.environ.get("WORLDOS_MCP_ISSUER_URL", "https://worldos.invalid/auth").strip()
    host = os.environ.get("WORLDOS_MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("WORLDOS_MCP_PORT", "8766"))

    mcp = FastMCP(
        "WorldOS",
        instructions=(
            "Semantic read and guarded control access to WorldOS. Always probe a world before mutation. "
            "Every mutation requires an explicit world identity, expected canonical hash, reason, and a unique "
            "idempotency key. Never infer a default world and never retry with a new key after an uncertain outcome."
        ),
        stateless_http=True,
        json_response=True,
        host=host,
        port=port,
        token_verifier=StaticMCPTokenVerifier(),
        auth=AuthSettings(
            issuer_url=AnyHttpUrl(issuer_url),
            resource_server_url=AnyHttpUrl(public_url),
            required_scopes=[READ_SCOPE],
        ),
    )

    @mcp.tool()
    def worldos_health() -> dict[str, Any]:
        """Return WorldOS runtime version and read-service capabilities."""
        return _service().health()

    @mcp.tool()
    def list_worlds() -> dict[str, Any]:
        """List worlds with explicit IDs, ticks, event counts and canonical hashes."""
        return _service().list_worlds()

    @mcp.tool()
    def probe_world(world_id: str, timeline: str = "main", limit: int = 50) -> dict[str, Any]:
        """Get a compact world probe: actors, social state, diagnostics and recent events."""
        return _service().probe_world(world_id, timeline=timeline, limit=limit)

    @mcp.tool()
    def inspect_actor(world_id: str, actor_id: str, timeline: str = "main") -> dict[str, Any]:
        """Inspect one actor including knowledge, memory, goals, plans and social state."""
        return _service().inspect_actor(world_id, actor_id, timeline=timeline)

    @mcp.tool()
    def query_events(world_id: str, timeline: str = "main", event_type: str | None = None, actor_id: str | None = None, subject_id: str | None = None, tick: int | None = None, correlation_id: str | None = None, limit: int = 100) -> dict[str, Any]:
        """Query the event log with optional semantic filters."""
        return _service().query_events(world_id, timeline=timeline, event_type=event_type, actor_id=actor_id, subject_id=subject_id, tick=tick, correlation_id=correlation_id, limit=limit)

    @mcp.tool()
    def inspect_social_graph(world_id: str, timeline: str = "main") -> dict[str, Any]:
        """Return social bonds and reciprocity obligations for a world timeline."""
        return _service().inspect_social_graph(world_id, timeline=timeline)

    @mcp.tool()
    def get_narrative_context(world_id: str, timeline: str = "main", actor_id: str | None = None, from_sequence: int = 1) -> dict[str, Any]:
        """Return narrator-ready read-only context without changing the world."""
        return _service().get_narrative_context(world_id, timeline=timeline, actor_id=actor_id, from_sequence=from_sequence)

    @mcp.tool()
    def diagnose_world(world_id: str, timeline: str = "main") -> dict[str, Any]:
        """Run structural diagnostics for event continuity, goals and social obligations."""
        return _service().get_diagnostics(world_id, timeline=timeline)

    @mcp.tool()
    def create_world(config: dict[str, Any], idempotency_key: str, reason: str) -> dict[str, Any]:
        """Create a world through the persistent idempotent Control API. Supply a unique stable key and reason."""
        return _control_request("POST", "/worlds", payload={"config": config, "idempotency_key": idempotency_key, "reason": reason}, idempotency_key=idempotency_key)

    @mcp.tool()
    def advance_world(world_id: str, ticks: int, expected_world_hash: str, idempotency_key: str, reason: str, timeline_id: str = "main") -> dict[str, Any]:
        """Advance an explicit world. Requires optimistic concurrency and persistent idempotency."""
        return _control_request("POST", f"/worlds/{world_id}/advance", payload={"ticks": ticks, "timeline_id": timeline_id, "expected_world_hash": expected_world_hash, "idempotency_key": idempotency_key, "reason": reason}, idempotency_key=idempotency_key)

    @mcp.tool()
    def branch_world(world_id: str, branch_id: str, expected_world_hash: str, idempotency_key: str, reason: str, timeline_id: str = "main", through_sequence: int | None = None) -> dict[str, Any]:
        """Create a timeline branch from an explicit world with hash precondition and idempotency."""
        payload = {"branch_id": branch_id, "timeline_id": timeline_id, "expected_world_hash": expected_world_hash, "idempotency_key": idempotency_key, "reason": reason}
        if through_sequence is not None:
            payload["through_sequence"] = through_sequence
        return _control_request("POST", f"/worlds/{world_id}/branch", payload=payload, idempotency_key=idempotency_key)

    @mcp.tool()
    def inject_world_event(world_id: str, event: dict[str, Any], expected_world_hash: str, idempotency_key: str, reason: str, timeline_id: str = "main") -> dict[str, Any]:
        """Append a non-tick event through the guarded Control API. Extension events may be projection-neutral."""
        return _control_request("POST", f"/worlds/{world_id}/inject-event", payload={"event": event, "timeline_id": timeline_id, "expected_world_hash": expected_world_hash, "idempotency_key": idempotency_key, "reason": reason}, idempotency_key=idempotency_key)

    @mcp.tool()
    def delete_world(world_id: str, expected_world_hash: str, idempotency_key: str, reason: str) -> dict[str, Any]:
        """Delete an explicit world using its current canonical hash. This operation is idempotency-ledger protected."""
        # reason is intentionally included in the tool contract/audit trail even though DELETE has no JSON body.
        if not reason.strip():
            raise ValueError("reason is required")
        return _control_request("DELETE", f"/worlds/{world_id}", idempotency_key=idempotency_key, if_match=expected_world_hash)

    @mcp.tool()
    def control_command_status(idempotency_key: str) -> dict[str, Any]:
        """Read the persistent outcome of a prior mutation before deciding whether a retry is safe."""
        return _control_request("GET", f"/commands/{idempotency_key}")

    return mcp


def main() -> None:
    build_mcp().run(transport="streamable-http")


if __name__ == "__main__":
    main()
