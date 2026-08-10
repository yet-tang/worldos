from __future__ import annotations

import asyncio

from worldos_core.agent_services import WorldReadService
from worldos_core.mcp_server import READ_SCOPE, StaticMCPTokenVerifier, build_mcp
from worldos_core.world_creator import WorldCatalog, WorldConfig


def test_world_read_service_exposes_semantic_world_views(tmp_path) -> None:
    legacy_db = tmp_path / "world.db"
    catalog = WorldCatalog(tmp_path, legacy_db_path=legacy_db)
    descriptor = catalog.create(
        WorldConfig(
            name="MCP测试镇",
            world_type="agrarian_town",
            era="agrarian",
            population=4,
            location_count=3,
            seed="mcp-read-test",
        )
    )

    service = WorldReadService(legacy_db)
    worlds = service.list_worlds()["worlds"]
    created = next(item for item in worlds if item["world_id"] == descriptor.world_id)
    assert created["current_tick"] == 0
    assert created["event_count"] > 0
    assert len(created["world_hash"]) == 64

    probe = service.probe_world(descriptor.world_id)
    assert probe["world"]["name"] == "MCP测试镇"
    assert probe["snapshot"]["actor_count"] == 4
    assert probe["snapshot"]["location_count"] == 3
    assert probe["diagnostics"]["status"] in {"ok", "warning"}

    actor_id = probe["actors"][0]["actor_id"]
    actor = service.inspect_actor(descriptor.world_id, actor_id)
    assert actor["actor_id"] == actor_id

    events = service.query_events(descriptor.world_id, event_type="entity.created", limit=10)
    assert events["matched"] >= 7
    assert len(events["events"]) <= 10

    social = service.inspect_social_graph(descriptor.world_id)
    assert isinstance(social, dict)

    narrative = service.get_narrative_context(descriptor.world_id)
    assert isinstance(narrative, dict)


def test_mcp_token_verifier_is_fail_closed(monkeypatch) -> None:
    verifier = StaticMCPTokenVerifier()
    monkeypatch.delenv("WORLDOS_MCP_TOKEN", raising=False)
    assert asyncio.run(verifier.verify_token("anything")) is None

    token = "a" * 64
    monkeypatch.setenv("WORLDOS_MCP_TOKEN", token)
    assert asyncio.run(verifier.verify_token("wrong")) is None
    access = asyncio.run(verifier.verify_token(token))
    assert access is not None
    assert READ_SCOPE in access.scopes


def test_mcp_server_builds_with_read_tools(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WORLDOS_DB", str(tmp_path / "world.db"))
    monkeypatch.setenv("WORLDOS_MCP_TOKEN", "b" * 64)
    monkeypatch.setenv("WORLDOS_MCP_PUBLIC_URL", "https://worldos.example/mcp")
    monkeypatch.setenv("WORLDOS_MCP_ISSUER_URL", "https://worldos.example/auth")
    server = build_mcp()
    assert server.name == "WorldOS"