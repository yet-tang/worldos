from __future__ import annotations

import asyncio

import pytest

from worldos_core.agent_services import WorldReadService
from worldos_core.mcp_server import READ_SCOPE, WRITE_SCOPE, StaticMCPTokenVerifier, _control_request, build_mcp
from worldos_core.world_creator import WorldCatalog, WorldConfig


def test_world_read_service_exposes_semantic_world_views(tmp_path) -> None:
    legacy_db = tmp_path / "world.db"
    catalog = WorldCatalog(tmp_path, legacy_db_path=legacy_db)
    descriptor = catalog.create(WorldConfig(name="MCP测试镇", world_type="agrarian_town", era="agrarian", population=4, location_count=3, seed="mcp-read-test"))
    service = WorldReadService(legacy_db)
    worlds = service.list_worlds()["worlds"]
    created = next(item for item in worlds if item["world_id"] == descriptor.world_id)
    assert created["current_tick"] == 0
    assert created["event_count"] > 0
    assert len(created["world_hash"]) == 64
    probe = service.probe_world(descriptor.world_id)
    assert probe["world"]["name"] == "MCP测试镇"
    assert probe["snapshot"]["actor_count"] == 4
    actor_id = probe["actors"][0]["actor_id"]
    assert service.inspect_actor(descriptor.world_id, actor_id)["actor_id"] == actor_id
    assert service.query_events(descriptor.world_id, event_type="entity.created", limit=10)["matched"] >= 7


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
    assert WRITE_SCOPE in access.scopes


def test_mcp_server_builds_with_control_tools(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WORLDOS_DB", str(tmp_path / "world.db"))
    monkeypatch.setenv("WORLDOS_MCP_TOKEN", "b" * 64)
    monkeypatch.setenv("WORLDOS_MCP_PUBLIC_URL", "https://worldos.example/mcp")
    monkeypatch.setenv("WORLDOS_MCP_ISSUER_URL", "https://worldos.example/auth")
    server = build_mcp()
    assert server.name == "WorldOS"


def test_control_bridge_fails_closed_without_control_token(monkeypatch) -> None:
    monkeypatch.delenv("WORLDOS_CONTROL_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="WORLDOS_CONTROL_TOKEN"):
        _control_request("GET", "/health")


def test_control_bridge_forwards_auth_idempotency_and_if_match(monkeypatch) -> None:
    monkeypatch.setenv("WORLDOS_CONTROL_TOKEN", "c" * 64)
    monkeypatch.setenv("WORLDOS_CONTROL_INTERNAL_URL", "http://inspector:8765/api/control")
    seen = {}

    class Response:
        status_code = 200
        headers = {"Idempotency-Replayed": "true"}
        text = ""
        def json(self):
            return {"ok": True}

    class Client:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def request(self, method, url, json=None, headers=None):
            seen.update(method=method, url=url, json=json, headers=headers)
            return Response()

    monkeypatch.setattr("worldos_core.mcp_server.httpx.Client", Client)
    result = _control_request("DELETE", "/worlds/w1", idempotency_key="k1", if_match="hash1")
    assert seen["headers"]["Authorization"] == "Bearer " + "c" * 64
    assert seen["headers"]["Idempotency-Key"] == "k1"
    assert seen["headers"]["If-Match"] == "hash1"
    assert result["idempotency_replayed"] is True
