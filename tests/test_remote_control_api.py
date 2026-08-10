from __future__ import annotations

from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import threading

from worldos_core.web_console_control import _current_state, make_console_handler
from worldos_core.world_creator import WorldCatalog


def _request(port: int, method: str, path: str, token: str, payload: dict | None = None, headers: dict | None = None):
    body = None if payload is None else json.dumps(payload).encode()
    request_headers = {"Authorization": f"Bearer {token}"}
    if body is not None:
        request_headers["Content-Type"] = "application/json"
        request_headers["Content-Length"] = str(len(body))
    request_headers.update(headers or {})
    connection = HTTPConnection("127.0.0.1", port, timeout=10)
    connection.request(method, path, body=body, headers=request_headers)
    response = connection.getresponse()
    document = json.loads(response.read().decode())
    connection.close()
    return response.status, document


def test_remote_control_create_advance_conflict_and_delete(tmp_path: Path, monkeypatch) -> None:
    token = "c" * 64
    monkeypatch.setenv("WORLDOS_CONTROL_TOKEN", token)
    legacy = tmp_path / "world.db"
    handler = make_console_handler(legacy)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, created = _request(
            server.server_port,
            "POST",
            "/api/control/worlds",
            token,
            {
                "name": "远程验收镇",
                "world_type": "agrarian_town",
                "era": "agrarian",
                "population": 4,
                "location_count": 3,
                "seed": "remote-control-test",
            },
        )
        assert status == 201
        world_id = created["world"]["world_id"]
        descriptor = WorldCatalog(tmp_path, legacy_db_path=legacy).get(world_id)
        before = _current_state(descriptor.database_path)

        status, conflict = _request(
            server.server_port,
            "POST",
            f"/api/control/worlds/{world_id}/advance",
            token,
            {
                "ticks": 1,
                "expected_world_hash": "stale",
                "idempotency_key": "conflict",
                "reason": "prove fail closed",
            },
        )
        assert status == 409
        assert "world hash conflict" in conflict["error"]
        assert _current_state(descriptor.database_path) == before

        status, advanced = _request(
            server.server_port,
            "POST",
            f"/api/control/worlds/{world_id}/advance",
            token,
            {
                "ticks": 1,
                "expected_world_hash": before["world_hash"],
                "idempotency_key": "advance-1",
                "reason": "remote acceptance test",
            },
        )
        assert status == 200
        assert advanced["after"]["current_tick"] == before["current_tick"] + 1
        assert advanced["after"]["event_count"] > before["event_count"]

        after = advanced["after"]
        status, deleted = _request(
            server.server_port,
            "DELETE",
            f"/api/control/worlds/{world_id}",
            token,
            headers={"If-Match": after["world_hash"]},
        )
        assert status == 200
        assert deleted["deleted"] == world_id
        assert not Path(descriptor.database_path).exists()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_remote_control_rejects_missing_or_short_token(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("WORLDOS_CONTROL_TOKEN", raising=False)
    handler = make_console_handler(tmp_path / "world.db")
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, payload = _request(server.server_port, "GET", "/api/control/health", "x" * 64)
        assert status == 404
        assert payload["error"] == "control api disabled"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
