from __future__ import annotations

import json
from http.server import ThreadingHTTPServer
from pathlib import Path
import threading
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from worldos_core.sqlite_store import SQLiteEventStore
from worldos_core.web_console_debug import make_console_handler
from worldos_core.world_creator import WorldCatalog, WorldConfig


TOKEN = "worldos-debug-test-token-0123456789"


def _request(url: str, *, method: str = "GET", headers: dict[str, str] | None = None):
    request = Request(url, method=method, headers=headers or {})
    try:
        with urlopen(request, timeout=10) as response:
            body = response.read().decode("utf-8")
            return response.status, dict(response.headers.items()), json.loads(body)
    except HTTPError as exc:
        body = exc.read().decode("utf-8")
        return exc.code, dict(exc.headers.items()), json.loads(body)


def _server(tmp_path: Path):
    handler = make_console_handler(tmp_path / "world.db")
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, f"http://127.0.0.1:{server.server_address[1]}"


def _stop(server: ThreadingHTTPServer, thread: threading.Thread) -> None:
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def test_debug_api_is_disabled_without_token(tmp_path, monkeypatch):
    monkeypatch.delenv("WORLDOS_DEBUG_TOKEN", raising=False)
    server, thread, base = _server(tmp_path)
    try:
        status, _, payload = _request(base + "/api/debug")
        assert status == 404
        assert payload["error"] == "debug api disabled"
    finally:
        _stop(server, thread)


def test_token_debug_api_reads_world_without_mutating_it(tmp_path, monkeypatch):
    catalog = WorldCatalog(tmp_path, legacy_db_path=tmp_path / "world.db")
    descriptor = catalog.create(
        WorldConfig(
            name="调试验证镇",
            world_type="agrarian_town",
            era="agrarian",
            population=4,
            location_count=3,
            resource_abundance=55,
            social_stability=60,
            conflicts=["resource_scarcity"],
            seed="debug-api-test",
        )
    )
    with SQLiteEventStore(descriptor.database_path) as store:
        before_events = len(store.read("main"))

    monkeypatch.setenv("WORLDOS_DEBUG_TOKEN", TOKEN)
    monkeypatch.setenv("WORLDOS_VCS_REF", "debug-test-sha")
    monkeypatch.setenv("WORLDOS_VERSION", "sha-debug-test")
    server, thread, base = _server(tmp_path)
    try:
        status, headers, payload = _request(base + "/api/debug")
        assert status == 401
        assert "Bearer" in headers.get("WWW-Authenticate", "")
        assert payload["error"] == "invalid or missing debug token"

        query = urlencode({"token": TOKEN})
        status, _, health = _request(base + "/api/debug/health?" + query)
        assert status == 200
        assert health["ok"] is True
        assert health["read_only"] is True
        assert health["runtime"]["vcs_ref"] == "debug-test-sha"
        assert "probe" in health["capabilities"]

        status, _, worlds = _request(base + "/api/debug/worlds?" + query)
        assert status == 200
        target = next(item for item in worlds["worlds"] if item["world_id"] == descriptor.world_id)
        assert target["name"] == "调试验证镇"
        assert target["event_count"] == before_events
        assert "database_path" not in target

        probe_query = urlencode({"token": TOKEN, "limit": 5})
        status, _, probe = _request(
            base + f"/api/debug/worlds/{quote(descriptor.world_id)}/probe?{probe_query}"
        )
        assert status == 200
        assert probe["runtime"]["vcs_ref"] == "debug-test-sha"
        assert probe["world"]["world_id"] == descriptor.world_id
        assert probe["snapshot"]["event_count"] == before_events
        assert probe["snapshot"]["actor_count"] == 4
        assert probe["snapshot"]["location_count"] == 3
        assert probe["diagnostics"]["sequence_contiguous"] is True
        assert len(probe["recent_events"]) <= 5
        assert len(probe["actors"]) == 4
        assert TOKEN not in json.dumps(probe, ensure_ascii=False)

        actor_id = probe["actors"][0]["actor_id"]
        status, _, actor = _request(
            base + f"/api/debug/worlds/{quote(descriptor.world_id)}/actor/{quote(actor_id)}?{query}"
        )
        assert status == 200
        assert actor["actor_id"] == actor_id
        assert actor["entity"]["components"]["identity"]["name"]

        events_query = urlencode({"token": TOKEN, "event_type": "world.created", "limit": 10})
        status, _, events = _request(
            base + f"/api/debug/worlds/{quote(descriptor.world_id)}/events?{events_query}"
        )
        assert status == 200
        assert events["matched"] == 1
        assert events["events"][0]["event_type"] == "world.created"
        event_id = events["events"][0]["event_id"]

        status, _, explained = _request(
            base
            + f"/api/debug/worlds/{quote(descriptor.world_id)}/explain-event/{quote(event_id)}?{query}"
        )
        assert status == 200
        assert explained["event"]["event_id"] == event_id

        status, _, social = _request(
            base + f"/api/debug/worlds/{quote(descriptor.world_id)}/social",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert status == 200
        assert "bonds_by_actor" in social
        assert "obligations" in social

        status, _, diagnostics = _request(
            base + f"/api/debug/worlds/{quote(descriptor.world_id)}/diagnostics?{query}"
        )
        assert status == 200
        assert diagnostics["sequence_contiguous"] is True

        status, _, narrative = _request(
            base + f"/api/debug/worlds/{quote(descriptor.world_id)}/narrative?{query}"
        )
        assert status == 200
        assert narrative["mode"] == "omniscient"

        with SQLiteEventStore(descriptor.database_path) as store:
            after_events = len(store.read("main"))
        assert after_events == before_events
    finally:
        _stop(server, thread)


def test_debug_api_rejects_short_configured_token(tmp_path, monkeypatch):
    monkeypatch.setenv("WORLDOS_DEBUG_TOKEN", "short")
    server, thread, base = _server(tmp_path)
    try:
        status, _, payload = _request(base + "/api/debug?token=short")
        assert status == 503
        assert payload["error"] == "debug api token is misconfigured"
    finally:
        _stop(server, thread)


def test_proxy_and_compose_protect_debug_token_usage():
    root = Path(__file__).resolve().parents[1]
    nginx = (root / "docker" / "nginx.conf").read_text(encoding="utf-8")
    compose = (root / "compose.yaml").read_text(encoding="utf-8")

    assert "location ^~ /api/debug/" in nginx
    debug_block = nginx.split("location ^~ /api/debug/", 1)[1].split("location /", 1)[0]
    assert "auth_basic off;" in debug_block
    assert "access_log off;" in debug_block
    assert "WORLDOS_DEBUG_TOKEN: ${WORLDOS_DEBUG_TOKEN:-}" in compose
