from __future__ import annotations

import hmac
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import threading
from typing import Any, Callable
from urllib.parse import parse_qs, unquote, urlparse

from .control_ledger import (
    CommandKeyConflict,
    CommandOutcomeUnknown,
    ControlCommandLedger,
)
from .events import NewEvent
from .inspector import WorldInspector
from .runner import WorldRunner
from .sqlite_store import SQLiteEventStore
from .web_console_debug import make_console_handler as make_debug_console_handler
from .web_inspector import _jsonable
from .world_creator import WorldCatalog, WorldConfig


CONTROL_PREFIX = "/api/control"
_CONTROL_LOCKS: dict[str, threading.Lock] = {}
_CONTROL_LOCKS_GUARD = threading.Lock()
_MAX_TICKS = 10_000


def _control_token() -> str:
    return os.environ.get("WORLDOS_CONTROL_TOKEN", "").strip()


def _provided_token(handler: BaseHTTPRequestHandler, query: dict[str, list[str]]) -> str:
    authorization = handler.headers.get("Authorization", "").strip()
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return handler.headers.get("X-WorldOS-Control-Token", "").strip() or query.get("token", [""])[0].strip()


def _authorized(handler: BaseHTTPRequestHandler, query: dict[str, list[str]]) -> bool:
    configured = _control_token()
    provided = _provided_token(handler, query)
    return bool(configured and provided and hmac.compare_digest(configured, provided))


def _lock_for(database_path: str | Path) -> threading.Lock:
    key = str(Path(database_path).resolve())
    with _CONTROL_LOCKS_GUARD:
        return _CONTROL_LOCKS.setdefault(key, threading.Lock())


def _current_state(database_path: str | Path, timeline: str = "main") -> dict[str, Any]:
    with SQLiteEventStore(database_path) as store:
        bundle = WorldInspector(store).bundle(timeline)
        completed = [event.tick for event in bundle.events if event.event_type == "tick.completed"]
        current_tick = max(completed, default=max((event.tick for event in bundle.events), default=0))
        return {
            "timeline_id": timeline,
            "current_tick": current_tick,
            "event_count": len(bundle.events),
            "world_hash": bundle.world.canonical_hash(),
        }


def _require_expected_hash(payload: dict[str, Any], state: dict[str, Any]) -> None:
    expected = str(payload.get("expected_world_hash") or "").strip()
    if not expected:
        raise ValueError("expected_world_hash is required for mutations")
    if expected != state["world_hash"]:
        raise RuntimeError(
            f"world hash conflict: expected {expected}, current {state['world_hash']}"
        )


def make_console_handler(database_path: str | Path) -> type[BaseHTTPRequestHandler]:
    legacy_database = Path(database_path)
    catalog = WorldCatalog(legacy_database.parent, legacy_db_path=legacy_database)
    ledger_path = legacy_database.parent / "control_commands.db"
    BaseHandler = make_debug_console_handler(database_path)

    class Handler(BaseHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == CONTROL_PREFIX or parsed.path.startswith(CONTROL_PREFIX + "/"):
                query = parse_qs(parsed.query)
                if not self._authorize_control(query):
                    return
                if parsed.path in {CONTROL_PREFIX, CONTROL_PREFIX + "/", CONTROL_PREFIX + "/health"}:
                    self._send(
                        HTTPStatus.OK,
                        {
                            "ok": True,
                            "write_enabled": True,
                            "persistent_idempotency": True,
                            "max_ticks_per_request": _MAX_TICKS,
                            "capabilities": [
                                "create-world",
                                "advance",
                                "branch",
                                "inject-event",
                                "delete-world",
                                "command-status",
                            ],
                        },
                    )
                    return
                command_prefix = CONTROL_PREFIX + "/commands/"
                if parsed.path.startswith(command_prefix):
                    key = unquote(parsed.path.removeprefix(command_prefix)).strip("/")
                    if not key or "/" in key:
                        self._send(HTTPStatus.BAD_REQUEST, {"error": "invalid idempotency_key"})
                        return
                    with ControlCommandLedger(ledger_path) as ledger:
                        command = ledger.get(key)
                    if command is None:
                        self._send(HTTPStatus.NOT_FOUND, {"error": "unknown command"})
                    else:
                        self._send(HTTPStatus.OK, command)
                    return
            super().do_GET()

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path != CONTROL_PREFIX and not parsed.path.startswith(CONTROL_PREFIX + "/"):
                super().do_POST()
                return
            query = parse_qs(parsed.query)
            if not self._authorize_control(query):
                return
            try:
                payload = self._read_control_json()
                self._dispatch_control_post(parsed.path, payload)
            except KeyError as exc:
                self._send(HTTPStatus.NOT_FOUND, {"error": str(exc)})
            except (CommandKeyConflict, CommandOutcomeUnknown, RuntimeError) as exc:
                self._send(HTTPStatus.CONFLICT, {"error": str(exc)})
            except (TypeError, ValueError) as exc:
                self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            except Exception as exc:
                self._send(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

        def do_DELETE(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if not parsed.path.startswith(CONTROL_PREFIX + "/worlds/"):
                super_method = getattr(super(), "do_DELETE", None)
                if super_method is None:
                    self._send(HTTPStatus.NOT_FOUND, {"error": "endpoint not found"})
                else:
                    super_method()
                return
            query = parse_qs(parsed.query)
            if not self._authorize_control(query):
                return

            world_id = unquote(parsed.path.removeprefix(CONTROL_PREFIX + "/worlds/")).strip("/")
            if not world_id or "/" in world_id:
                self._send(HTTPStatus.BAD_REQUEST, {"error": "invalid world_id"})
                return
            idempotency_key = self._idempotency_key({})
            if_match = self.headers.get("If-Match", "").strip().strip('"')
            if not if_match:
                self._send(HTTPStatus.BAD_REQUEST, {"error": "If-Match world hash is required for deletion"})
                return
            fingerprint = ControlCommandLedger.fingerprint(
                "DELETE", parsed.path, None, if_match=if_match
            )

            def mutate() -> tuple[HTTPStatus, dict[str, Any]]:
                descriptor = catalog.get(world_id)
                state = _current_state(descriptor.database_path)
                if if_match != state["world_hash"]:
                    raise RuntimeError(
                        f"world hash conflict: expected {if_match}, current {state['world_hash']}"
                    )
                deleted = catalog.delete(world_id)
                return HTTPStatus.OK, {"deleted": deleted.world_id, "previous_state": state}

            self._run_idempotent(idempotency_key, fingerprint, "DELETE", parsed.path, mutate)

        def _authorize_control(self, query: dict[str, list[str]]) -> bool:
            configured = _control_token()
            if not configured:
                self._send(HTTPStatus.NOT_FOUND, {"error": "control api disabled"})
                return False
            if len(configured) < 32:
                self._send(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "control api token is misconfigured"})
                return False
            if not _authorized(self, query):
                self._send(
                    HTTPStatus.UNAUTHORIZED,
                    {"error": "invalid or missing control token"},
                    extra_headers={"WWW-Authenticate": 'Bearer realm="WorldOS Control API"'},
                )
                return False
            return True

        def _read_control_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 0 or length > 1_000_000:
                raise ValueError("request body too large")
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            if not isinstance(payload, dict):
                raise ValueError("request body must be a JSON object")
            return payload

        def _idempotency_key(self, payload: dict[str, Any]) -> str:
            key = self.headers.get("Idempotency-Key", "").strip()
            if not key:
                key = str(payload.get("idempotency_key") or "").strip()
            if not key:
                raise ValueError("idempotency_key is required for mutations")
            return key

        def _run_idempotent(
            self,
            idempotency_key: str,
            fingerprint: str,
            method: str,
            path: str,
            mutate: Callable[[], tuple[HTTPStatus, dict[str, Any]]],
        ) -> None:
            with ControlCommandLedger(ledger_path) as ledger:
                replay = ledger.reserve(
                    idempotency_key,
                    fingerprint,
                    method=method,
                    path=path,
                )
                if replay is not None:
                    self._send(
                        HTTPStatus(replay.status_code),
                        replay.response,
                        extra_headers={"Idempotency-Replayed": "true"},
                    )
                    return

            mutation_started = False
            try:
                # mutate() performs all fail-closed validation before its first write.
                mutation_started = True
                status, response = mutate()
                with ControlCommandLedger(ledger_path) as ledger:
                    ledger.complete(
                        idempotency_key,
                        status_code=int(status),
                        response=response,
                    )
                self._send(status, response)
            except (KeyError, TypeError, ValueError, RuntimeError, CommandKeyConflict):
                # These exceptions are expected validation/concurrency failures in the
                # current implementation and happen before a committed side effect.
                # RuntimeError is only raised by explicit pre-write guards here.
                if mutation_started:
                    with ControlCommandLedger(ledger_path) as ledger:
                        ledger.release(idempotency_key)
                raise
            except Exception:
                # Unknown failures are deliberately NOT released. A command may have
                # committed before the process/handler failed, so retries must fail closed.
                raise

        def _dispatch_control_post(self, path: str, payload: dict[str, Any]) -> None:
            idempotency_key = self._idempotency_key(payload)

            if path == CONTROL_PREFIX + "/worlds":
                config_payload = payload.get("config", payload)
                if not isinstance(config_payload, dict):
                    raise ValueError("config must be an object")
                config_payload = dict(config_payload)
                config_payload.pop("reason", None)
                config_payload.pop("idempotency_key", None)
                config = WorldConfig.model_validate(config_payload)
                fingerprint = ControlCommandLedger.fingerprint("POST", path, payload)

                def create_world() -> tuple[HTTPStatus, dict[str, Any]]:
                    descriptor = catalog.create(config)
                    return HTTPStatus.CREATED, {"world": _jsonable(descriptor)}

                self._run_idempotent(
                    idempotency_key, fingerprint, "POST", path, create_world
                )
                return

            prefix = CONTROL_PREFIX + "/worlds/"
            if not path.startswith(prefix):
                self._send(HTTPStatus.NOT_FOUND, {"error": "control endpoint not found"})
                return
            parts = [unquote(part) for part in path.removeprefix(prefix).strip("/").split("/") if part]
            if len(parts) != 2:
                self._send(HTTPStatus.NOT_FOUND, {"error": "control endpoint not found"})
                return
            world_id, action = parts
            timeline = str(payload.get("timeline_id") or "main")

            # Validate command-specific shape before reserving the key. Replays still work
            # after the target world disappears because descriptor lookup happens in mutate.
            ticks: int | None = None
            branch_id = ""
            through_sequence: Any = None
            event: NewEvent | None = None
            if action == "advance":
                ticks = int(payload.get("ticks", 0))
                if ticks < 1 or ticks > _MAX_TICKS:
                    raise ValueError(f"ticks must be between 1 and {_MAX_TICKS}")
            elif action == "branch":
                branch_id = str(payload.get("branch_id") or "").strip()
                if not branch_id:
                    raise ValueError("branch_id is required")
                through_sequence = payload.get("through_sequence")
            elif action == "inject-event":
                event_payload = payload.get("event")
                if not isinstance(event_payload, dict):
                    raise ValueError("event must be an object")
                event = NewEvent.model_validate(event_payload)
                if event.event_type in {"tick.started", "tick.completed"}:
                    raise ValueError("tick boundary events cannot be injected")
            else:
                self._send(HTTPStatus.NOT_FOUND, {"error": "control endpoint not found"})
                return

            fingerprint = ControlCommandLedger.fingerprint("POST", path, payload)

            def mutate_world() -> tuple[HTTPStatus, dict[str, Any]]:
                descriptor = catalog.get(world_id)
                database = Path(descriptor.database_path)
                lock = _lock_for(database)
                if not lock.acquire(blocking=False):
                    raise RuntimeError("world is busy")
                try:
                    before = _current_state(database, timeline)
                    _require_expected_hash(payload, before)
                    reason = str(payload.get("reason") or "remote control").strip()[:500]

                    if action == "advance":
                        assert ticks is not None
                        with WorldRunner(database, timeline_id=timeline) as runner:
                            result = runner.step(ticks, force=True)
                        after = _current_state(database, timeline)
                        return HTTPStatus.OK, {
                            "command": "advance",
                            "idempotency_key": idempotency_key,
                            "reason": reason,
                            "ticks_requested": ticks,
                            "ticks_run": len(result.tick_results),
                            "before": before,
                            "after": after,
                        }

                    if action == "branch":
                        with SQLiteEventStore(database) as store:
                            created = store.create_timeline(
                                branch_id,
                                parent_timeline_id=timeline,
                                parent_through_sequence=int(through_sequence) if through_sequence is not None else None,
                            )
                        return HTTPStatus.CREATED, {
                            "command": "branch",
                            "idempotency_key": idempotency_key,
                            "timeline": _jsonable(created),
                            "reason": reason,
                        }

                    assert action == "inject-event" and event is not None
                    with SQLiteEventStore(database) as store:
                        current = len(store.read(timeline))
                        committed = store.append_batch(
                            timeline, [event], expected_sequence=current
                        )
                    after = _current_state(database, timeline)
                    return HTTPStatus.CREATED, {
                        "command": "inject-event",
                        "idempotency_key": idempotency_key,
                        "reason": reason,
                        "event": _jsonable(committed[0]),
                        "before": before,
                        "after": after,
                    }
                finally:
                    lock.release()

            self._run_idempotent(
                idempotency_key, fingerprint, "POST", path, mutate_world
            )

    return Handler


def serve_world_console(
    database_path: str | Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> None:
    if not 0 < port < 65536:
        raise ValueError("port must be between 1 and 65535")
    server = ThreadingHTTPServer((host, port), make_console_handler(database_path))
    try:
        server.serve_forever()
    finally:
        server.server_close()
