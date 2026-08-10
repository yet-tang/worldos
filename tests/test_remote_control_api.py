from __future__ import annotations

from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import threading

from worldos_core.web_console_control import _current_state, make_console_handler
from worldos_core.world_creator import WorldCatalog


def _request(
    port: int,
    method: str,
    path: str,
    token: str,
    payload: dict | None = None,
    headers: dict | None = None,
):
    body = None if payload is None else json.dumps(payload).encode()
    request_headers = {"Authorization": f"Bearer {token}"}
    if body is not None:
        request_headers["Content-Type"] = "application/json"
        request_headers["Content-Length"] = str(len(body))
    request_headers.update(headers or {})
    connection = HTTPConnection("127.0.0.1", port, timeout=10)
    connection.request(method, path, body=body, headers=request_headers)
    response = connection.getresponse()
    response_headers = dict(response.getheaders())
    document = json.loads(response.read().decode())
    status = response.status
    connection.close()
    return status, document, response_headers


def _start_server(legacy: Path):
    handler = make_console_handler(legacy)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _stop_server(server: ThreadingHTTPServer, thread: threading.Thread) -> None:
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def test_remote_control_create_advance_replay_conflict_and_delete(tmp_path: Path, monkeypatch) -> None:
    token = "c" * 64
    monkeypatch.setenv("WORLDOS_CONTROL_TOKEN", token)
    legacy = tmp_path / "world.db"
    server, thread = _start_server(legacy)
    try:
        create_payload = {
            "name": "远程验收镇",
            "world_type": "agrarian_town",
            "era": "agrarian",
            "population": 4,
            "location_count": 3,
            "seed": "remote-control-test",
            "idempotency_key": "create-1",
            "reason": "create test world",
        }
        status, created, _ = _request(
            server.server_port,
            "POST",
            "/api/control/worlds",
            token,
            create_payload,
        )
        assert status == 201
        world_id = created["world"]["world_id"]

        # Replaying create returns the original response and does not create a -2 world.
        status, replayed_create, headers = _request(
            server.server_port,
            "POST",
            "/api/control/worlds",
            token,
            create_payload,
        )
        assert status == 201
        assert replayed_create == created
        assert headers["Idempotency-Replayed"] == "true"
        assert len(WorldCatalog(tmp_path, legacy_db_path=legacy).list_worlds()) == 1

        descriptor = WorldCatalog(tmp_path, legacy_db_path=legacy).get(world_id)
        before = _current_state(descriptor.database_path)

        status, conflict, _ = _request(
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

        advance_payload = {
            "ticks": 1,
            "expected_world_hash": before["world_hash"],
            "idempotency_key": "advance-1",
            "reason": "remote acceptance test",
        }
        status, advanced, _ = _request(
            server.server_port,
            "POST",
            f"/api/control/worlds/{world_id}/advance",
            token,
            advance_payload,
        )
        assert status == 200
        assert advanced["after"]["current_tick"] == before["current_tick"] + 1
        assert advanced["after"]["event_count"] > before["event_count"]
        after = advanced["after"]

        # Same key + same request must replay even though expected_world_hash is now stale.
        status, replayed_advance, headers = _request(
            server.server_port,
            "POST",
            f"/api/control/worlds/{world_id}/advance",
            token,
            advance_payload,
        )
        assert status == 200
        assert replayed_advance == advanced
        assert headers["Idempotency-Replayed"] == "true"
        assert _current_state(descriptor.database_path) == after

        # Same key cannot be reused for a different command body.
        status, key_conflict, _ = _request(
            server.server_port,
            "POST",
            f"/api/control/worlds/{world_id}/advance",
            token,
            {**advance_payload, "ticks": 2},
        )
        assert status == 409
        assert "different command" in key_conflict["error"]
        assert _current_state(descriptor.database_path) == after

        status, command, _ = _request(
            server.server_port,
            "GET",
            "/api/control/commands/advance-1",
            token,
        )
        assert status == 200
        assert command["state"] == "completed"
        assert command["status_code"] == 200
        assert command["response"] == advanced

        delete_headers = {
            "If-Match": after["world_hash"],
            "Idempotency-Key": "delete-1",
        }
        status, deleted, _ = _request(
            server.server_port,
            "DELETE",
            f"/api/control/worlds/{world_id}",
            token,
            headers=delete_headers,
        )
        assert status == 200
        assert deleted["deleted"] == world_id
        assert not Path(descriptor.database_path).exists()

        # Delete replay succeeds even though the world database/catalog entry is gone.
        status, replayed_delete, headers = _request(
            server.server_port,
            "DELETE",
            f"/api/control/worlds/{world_id}",
            token,
            headers=delete_headers,
        )
        assert status == 200
        assert replayed_delete == deleted
        assert headers["Idempotency-Replayed"] == "true"
    finally:
        _stop_server(server, thread)


def test_idempotency_replay_survives_server_restart(tmp_path: Path, monkeypatch) -> None:
    token = "r" * 64
    monkeypatch.setenv("WORLDOS_CONTROL_TOKEN", token)
    legacy = tmp_path / "world.db"

    server, thread = _start_server(legacy)
    create_payload = {
        "name": "重启幂等镇",
        "world_type": "agrarian_town",
        "era": "agrarian",
        "population": 3,
        "location_count": 3,
        "seed": "restart-idempotency",
        "idempotency_key": "restart-create",
    }
    try:
        status, created, _ = _request(
            server.server_port, "POST", "/api/control/worlds", token, create_payload
        )
        assert status == 201
    finally:
        _stop_server(server, thread)

    assert (tmp_path / "control_commands.db").exists()

    server, thread = _start_server(legacy)
    try:
        status, replayed, headers = _request(
            server.server_port, "POST", "/api/control/worlds", token, create_payload
        )
        assert status == 201
        assert replayed == created
        assert headers["Idempotency-Replayed"] == "true"
        assert len(WorldCatalog(tmp_path, legacy_db_path=legacy).list_worlds()) == 1
    finally:
        _stop_server(server, thread)


def test_remote_control_rejects_missing_or_short_token(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("WORLDOS_CONTROL_TOKEN", raising=False)
    handler = make_console_handler(tmp_path / "world.db")
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, payload, _ = _request(server.server_port, "GET", "/api/control/health", "x" * 64)
        assert status == 404
        assert payload["error"] == "control api disabled"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
