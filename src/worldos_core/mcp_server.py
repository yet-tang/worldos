from __future__ import annotations

import hmac
import os
from pathlib import Path
from typing import Any

from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from pydantic import AnyHttpUrl

from .agent_services import WorldReadService


READ_SCOPE = "world:read"


class StaticMCPTokenVerifier(TokenVerifier):
    async def verify_token(self, token: str) -> AccessToken | None:
        configured = os.environ.get("WORLDOS_MCP_TOKEN", "").strip()
        if not configured or len(configured) < 32:
            return None
        if not hmac.compare_digest(configured, token):
            return None
        return AccessToken(token=token, client_id="worldos-agent", scopes=[READ_SCOPE])


def _database_path() -> Path:
    return Path(os.environ.get("WORLDOS_DB", "/data/world.db"))


def _service() -> WorldReadService:
    return WorldReadService(_database_path())


def build_mcp() -> FastMCP:
    public_url = os.environ.get("WORLDOS_MCP_PUBLIC_URL", "https://worldos.invalid/mcp").strip()
    issuer_url = os.environ.get("WORLDOS_MCP_ISSUER_URL", "https://worldos.invalid/auth").strip()
    host = os.environ.get("WORLDOS_MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("WORLDOS_MCP_PORT", "8766"))

    mcp = FastMCP(
        "WorldOS",
        instructions=(
            "Read-only semantic access to WorldOS worlds. Use probe_world before deeper inspection; "
            "treat world_id and timeline as explicit identities and do not infer a default world."
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
    def query_events(
        world_id: str,
        timeline: str = "main",
        event_type: str | None = None,
        actor_id: str | None = None,
        subject_id: str | None = None,
        tick: int | None = None,
        correlation_id: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Query the event log with optional semantic filters."""
        return _service().query_events(
            world_id,
            timeline=timeline,
            event_type=event_type,
            actor_id=actor_id,
            subject_id=subject_id,
            tick=tick,
            correlation_id=correlation_id,
            limit=limit,
        )

    @mcp.tool()
    def inspect_social_graph(world_id: str, timeline: str = "main") -> dict[str, Any]:
        """Return social bonds and reciprocity obligations for a world timeline."""
        return _service().inspect_social_graph(world_id, timeline=timeline)

    @mcp.tool()
    def get_narrative_context(
        world_id: str,
        timeline: str = "main",
        actor_id: str | None = None,
        from_sequence: int = 1,
    ) -> dict[str, Any]:
        """Return narrator-ready read-only context without changing the world."""
        return _service().get_narrative_context(
            world_id,
            timeline=timeline,
            actor_id=actor_id,
            from_sequence=from_sequence,
        )

    @mcp.tool()
    def diagnose_world(world_id: str, timeline: str = "main") -> dict[str, Any]:
        """Run structural diagnostics for event continuity, goals and social obligations."""
        return _service().get_diagnostics(world_id, timeline=timeline)

    return mcp


def main() -> None:
    # The process stays healthy even before a token is configured. The verifier
    # rejects every request until WORLDOS_MCP_TOKEN is a valid secret.
    build_mcp().run(transport="streamable-http")


if __name__ == "__main__":
    main()