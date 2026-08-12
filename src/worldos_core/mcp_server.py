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
from .experiments import compare_probes
from .semantic_stimulus import SemanticStimulus, semantic_event

READ_SCOPE = "world:read"
WRITE_SCOPE = "world:write"

class StaticMCPTokenVerifier(TokenVerifier):
    async def verify_token(self, token: str) -> AccessToken | None:
        configured = os.environ.get("WORLDOS_MCP_TOKEN", "").strip()
        if not configured or len(configured) < 32 or not hmac.compare_digest(configured, token):
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

def _control_request(method: str, path: str, *, payload: dict[str, Any] | None = None, idempotency_key: str | None = None, if_match: str | None = None) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {_control_token()}"}
    if idempotency_key: headers["Idempotency-Key"] = idempotency_key
    if if_match: headers["If-Match"] = if_match
    with httpx.Client(timeout=120.0) as client:
        response = client.request(method, _control_base_url() + path, json=payload, headers=headers)
    try: body = response.json()
    except ValueError: body = {"error": response.text}
    if response.status_code >= 400:
        raise RuntimeError(f"WorldOS Control API {response.status_code}: {body.get('error', body)}")
    if isinstance(body, dict):
        body["http_status"] = response.status_code
        body["idempotency_replayed"] = response.headers.get("Idempotency-Replayed", "").lower() == "true"
    return body

def build_mcp() -> FastMCP:
    public_url = os.environ.get("WORLDOS_MCP_PUBLIC_URL", "https://worldos.invalid/mcp").strip()
    issuer_url = os.environ.get("WORLDOS_MCP_ISSUER_URL", "https://worldos.invalid/auth").strip()
    mcp = FastMCP("WorldOS", instructions="Observe first, mutate explicit worlds only, preserve hashes and idempotency keys, and prefer semantic stimuli for experiments.", stateless_http=True, json_response=True, host=os.environ.get("WORLDOS_MCP_HOST", "0.0.0.0"), port=int(os.environ.get("WORLDOS_MCP_PORT", "8766")), token_verifier=StaticMCPTokenVerifier(), auth=AuthSettings(issuer_url=AnyHttpUrl(issuer_url), resource_server_url=AnyHttpUrl(public_url), required_scopes=[READ_SCOPE]))

    @mcp.tool()
    def worldos_health() -> dict[str, Any]: return _service().health()
    @mcp.tool()
    def list_worlds() -> dict[str, Any]: return _service().list_worlds()
    @mcp.tool()
    def probe_world(world_id: str, timeline: str = "main", limit: int = 50) -> dict[str, Any]: return _service().probe_world(world_id, timeline=timeline, limit=limit)
    @mcp.tool()
    def get_timeline_lineage(world_id: str, timeline: str = "main") -> dict[str, Any]: return _service().get_timeline_lineage(world_id, timeline=timeline)
    @mcp.tool()
    def inspect_actor(world_id: str, actor_id: str, timeline: str = "main") -> dict[str, Any]: return _service().inspect_actor(world_id, actor_id, timeline=timeline)
    @mcp.tool()
    def query_events(world_id: str, timeline: str = "main", event_type: str | None = None, actor_id: str | None = None, subject_id: str | None = None, tick: int | None = None, correlation_id: str | None = None, limit: int = 100) -> dict[str, Any]: return _service().query_events(world_id, timeline=timeline, event_type=event_type, actor_id=actor_id, subject_id=subject_id, tick=tick, correlation_id=correlation_id, limit=limit)
    @mcp.tool()
    def inspect_social_graph(world_id: str, timeline: str = "main") -> dict[str, Any]: return _service().inspect_social_graph(world_id, timeline=timeline)
    @mcp.tool()
    def get_narrative_context(world_id: str, timeline: str = "main", actor_id: str | None = None, from_sequence: int = 1) -> dict[str, Any]: return _service().get_narrative_context(world_id, timeline=timeline, actor_id=actor_id, from_sequence=from_sequence)
    @mcp.tool()
    def diagnose_world(world_id: str, timeline: str = "main") -> dict[str, Any]: return _service().get_diagnostics(world_id, timeline=timeline)
    @mcp.tool()
    def create_world(config: dict[str, Any], idempotency_key: str, reason: str) -> dict[str, Any]: return _control_request("POST", "/worlds", payload={"config": config, "idempotency_key": idempotency_key, "reason": reason}, idempotency_key=idempotency_key)
    @mcp.tool()
    def advance_world(world_id: str, ticks: int, expected_world_hash: str, idempotency_key: str, reason: str, timeline_id: str = "main") -> dict[str, Any]: return _control_request("POST", f"/worlds/{world_id}/advance", payload={"ticks": ticks, "timeline_id": timeline_id, "expected_world_hash": expected_world_hash, "idempotency_key": idempotency_key, "reason": reason}, idempotency_key=idempotency_key)
    @mcp.tool()
    def branch_world(world_id: str, branch_id: str, expected_world_hash: str, idempotency_key: str, reason: str, timeline_id: str = "main", through_sequence: int | None = None) -> dict[str, Any]:
        payload = {"branch_id": branch_id, "timeline_id": timeline_id, "expected_world_hash": expected_world_hash, "idempotency_key": idempotency_key, "reason": reason}
        if through_sequence is not None: payload["through_sequence"] = through_sequence
        return _control_request("POST", f"/worlds/{world_id}/branch", payload=payload, idempotency_key=idempotency_key)
    @mcp.tool()
    def inject_world_event(world_id: str, event: dict[str, Any], expected_world_hash: str, idempotency_key: str, reason: str, timeline_id: str = "main") -> dict[str, Any]: return _control_request("POST", f"/worlds/{world_id}/inject-event", payload={"event": event, "timeline_id": timeline_id, "expected_world_hash": expected_world_hash, "idempotency_key": idempotency_key, "reason": reason}, idempotency_key=idempotency_key)
    @mcp.tool()
    def apply_semantic_stimulus(world_id: str, stimulus: dict[str, Any], expected_world_hash: str, idempotency_key: str, reason: str, timeline_id: str = "main", experiment_id: str | None = None) -> dict[str, Any]:
        """Apply a typed external intervention: resource shock, environment event, information, social incident, or policy change."""
        probe = _service().probe_world(world_id, timeline=timeline_id, limit=1)
        snapshot = probe["snapshot"]
        current_hash = snapshot["world_hash"]
        if current_hash != expected_world_hash:
            raise ValueError(f"world hash conflict: expected {expected_world_hash}, current {current_hash}")
        tick = int(snapshot["current_tick"])
        event = semantic_event(tick=tick, stimulus=SemanticStimulus.model_validate(stimulus), experiment_id=experiment_id)
        return _control_request("POST", f"/worlds/{world_id}/inject-event", payload={"event": event, "timeline_id": timeline_id, "expected_world_hash": expected_world_hash, "idempotency_key": idempotency_key, "reason": reason}, idempotency_key=idempotency_key)
    @mcp.tool()
    def compare_timelines(world_id: str, control_timeline: str, experiment_timeline: str, limit: int = 50) -> dict[str, Any]:
        """Compare two timeline probes deterministically without mutation."""
        return compare_probes(_service().probe_world(world_id, timeline=control_timeline, limit=limit), _service().probe_world(world_id, timeline=experiment_timeline, limit=limit))
    @mcp.tool()
    def delete_world(world_id: str, expected_world_hash: str, idempotency_key: str, reason: str) -> dict[str, Any]:
        if not reason.strip(): raise ValueError("reason is required")
        return _control_request("DELETE", f"/worlds/{world_id}", idempotency_key=idempotency_key, if_match=expected_world_hash)
    @mcp.tool()
    def control_command_status(idempotency_key: str) -> dict[str, Any]: return _control_request("GET", f"/commands/{idempotency_key}")
    return mcp

def main() -> None: build_mcp().run(transport="streamable-http")
if __name__ == "__main__": main()
