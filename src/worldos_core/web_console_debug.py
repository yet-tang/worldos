from __future__ import annotations

from collections import Counter, defaultdict
import hmac
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from .inspector import WorldInspector
from .narrator import NarratorReadAPI
from .sqlite_store import SQLiteEventStore
from .web_console_story import make_console_handler as make_story_console_handler
from .web_inspector import WebInspectorService, _jsonable
from .world_creator import WorldCatalog, WorldDescriptor


DEBUG_PREFIX = "/api/debug"
_MAX_EVENT_LIMIT = 1000
_DEFAULT_EVENT_LIMIT = 100


def _debug_token() -> str:
    return os.environ.get("WORLDOS_DEBUG_TOKEN", "").strip()


def _runtime_meta() -> dict[str, str]:
    return {
        "vcs_ref": os.environ.get("WORLDOS_VCS_REF", "unknown"),
        "version": os.environ.get("WORLDOS_VERSION", "dev"),
    }


def _descriptor_payload(descriptor: WorldDescriptor) -> dict[str, Any]:
    return {
        "world_id": descriptor.world_id,
        "name": descriptor.name,
        "world_type": descriptor.world_type,
        "era": descriptor.era,
        "population": descriptor.population,
        "location_count": descriptor.location_count,
        "seed": descriptor.seed,
        "created_at": descriptor.created_at,
        "legacy": descriptor.legacy,
    }


def _provided_token(handler: BaseHTTPRequestHandler, query: dict[str, list[str]]) -> str:
    authorization = handler.headers.get("Authorization", "").strip()
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    header_token = handler.headers.get("X-WorldOS-Debug-Token", "").strip()
    if header_token:
        return header_token
    return query.get("token", [""])[0].strip()


def _is_authorized(handler: BaseHTTPRequestHandler, query: dict[str, list[str]]) -> bool:
    configured = _debug_token()
    if not configured:
        return False
    provided = _provided_token(handler, query)
    if not provided:
        return False
    return hmac.compare_digest(configured, provided)


def _parse_limit(query: dict[str, list[str]], *, default: int = _DEFAULT_EVENT_LIMIT) -> int:
    limit = int(query.get("limit", [str(default)])[0])
    if limit < 1 or limit > _MAX_EVENT_LIMIT:
        raise ValueError(f"limit must be between 1 and {_MAX_EVENT_LIMIT}")
    return limit


def _actor_name(entity_id: str, world: Any) -> str:
    entity = world.entities.get(entity_id)
    if entity is None:
        return entity_id
    identity = entity.components.get("identity", {})
    if isinstance(identity, dict):
        return str(identity.get("name") or entity_id)
    return entity_id


def _current_tick(events: list[Any]) -> int:
    completed = [event.tick for event in events if event.event_type == "tick.completed"]
    if completed:
        return max(completed)
    return max((event.tick for event in events), default=0)


def _diagnostics(bundle: Any) -> dict[str, Any]:
    events = bundle.events
    world = bundle.world
    planning = bundle.planning
    social = bundle.social
    current_tick = _current_tick(events)

    expected = list(range(1, len(events) + 1))
    actual = [event.sequence for event in events]
    sequence_contiguous = actual == expected

    started: Counter[int] = Counter()
    completed: Counter[int] = Counter()
    rejected: list[dict[str, Any]] = []
    event_types: Counter[str] = Counter()
    phases: Counter[str] = Counter()
    for event in events:
        event_types[event.event_type] += 1
        phases[event.phase] += 1
        if event.event_type == "tick.started":
            started[event.tick] += 1
        elif event.event_type == "tick.completed":
            completed[event.tick] += 1
        elif event.event_type == "intent.rejected":
            rejected.append(_jsonable(event))

    incomplete_ticks = sorted(tick for tick, count in started.items() if count > completed.get(tick, 0))
    duplicate_completed_ticks = sorted(tick for tick, count in completed.items() if count > 1)

    entity_ids = set(world.entities)
    orphan_relationships: list[dict[str, str]] = []
    for actor_id, entity in sorted(world.entities.items()):
        relationships = entity.components.get("relationships", {})
        if not isinstance(relationships, dict):
            continue
        for other_id in sorted(str(key) for key in relationships):
            if other_id not in entity_ids:
                orphan_relationships.append({"actor_id": actor_id, "other_id": other_id})

    overdue_obligations = [
        _jsonable(item)
        for item in social.obligations.values()
        if item.status == "open" and item.due_tick <= current_tick
    ]
    overdue_obligations.sort(key=lambda item: (item["due_tick"], item["obligation_id"]))

    stalled_active_goals: list[dict[str, Any]] = []
    for owner_id, goals in sorted(planning.goals_by_owner.items()):
        for goal in sorted(goals.values(), key=lambda item: item.goal_id):
            if goal.status != "active" or goal.created_tick >= current_tick:
                continue
            steps = planning.steps_by_goal.get(goal.goal_id, {})
            if steps and any(step.status in {"pending", "selected"} for step in steps.values()):
                continue
            stalled_active_goals.append(
                {
                    "owner_id": owner_id,
                    "goal_id": goal.goal_id,
                    "goal_type": goal.goal_type,
                    "created_tick": goal.created_tick,
                    "step_count": len(steps),
                }
            )

    warnings: list[str] = []
    if not sequence_contiguous:
        warnings.append("event sequence is not contiguous")
    if incomplete_ticks:
        warnings.append("one or more ticks started without completion")
    if duplicate_completed_ticks:
        warnings.append("one or more ticks have duplicate completion events")
    if orphan_relationships:
        warnings.append("relationship references unknown entities")
    if overdue_obligations:
        warnings.append("open social obligations are already overdue")
    if stalled_active_goals:
        warnings.append("active goals exist without pending work")

    return {
        "status": "ok" if not warnings else "warning",
        "warnings": warnings,
        "sequence_contiguous": sequence_contiguous,
        "incomplete_ticks": incomplete_ticks,
        "duplicate_completed_ticks": duplicate_completed_ticks,
        "orphan_relationships": orphan_relationships,
        "overdue_obligations": overdue_obligations,
        "stalled_active_goals": stalled_active_goals,
        "recent_rejected_intents": rejected[-20:],
        "event_type_counts": dict(event_types.most_common()),
        "phase_counts": dict(phases.most_common()),
    }


def _actor_probe(bundle: Any, actor_id: str) -> dict[str, Any]:
    entity = bundle.world.entities[actor_id]
    components = entity.components
    active_goals = [
        goal
        for goal in bundle.planning.active_goals(actor_id)
    ]
    bonds = list(bundle.social.bonds_by_actor.get(actor_id, {}).values())
    bonds.sort(key=lambda item: (-item.trust, -item.affinity, item.other_id))
    return {
        "actor_id": actor_id,
        "name": _actor_name(actor_id, bundle.world),
        "kind": entity.kind,
        "active": entity.active,
        "location_id": components.get("position", {}).get("location_id"),
        "health": components.get("health", {}),
        "needs": components.get("needs", components.get("survival", {})),
        "inventory": components.get("inventory", {}),
        "wallet": components.get("wallet"),
        "job": components.get("job", {}),
        "personality": components.get("personality", {}),
        "drives": components.get("drives", {}),
        "active_goals": [_jsonable(goal) for goal in active_goals],
        "social_bonds": [
            {**_jsonable(bond), "label": bond.label(), "other_name": _actor_name(bond.other_id, bundle.world)}
            for bond in bonds
        ],
        "obligations_as_debtor": [
            _jsonable(item) for item in bundle.social.open_obligations_for_debtor(actor_id)
        ],
        "obligations_as_creditor": [
            _jsonable(item) for item in bundle.social.open_obligations_for_creditor(actor_id)
        ],
    }


def _probe(store: SQLiteEventStore, descriptor: WorldDescriptor, timeline: str, limit: int) -> dict[str, Any]:
    inspector = WorldInspector(store)
    bundle = inspector.bundle(timeline)
    world = bundle.world
    actors = [
        entity_id
        for entity_id, entity in sorted(world.entities.items())
        if entity.kind in {"human", "character"}
    ]
    locations = [
        entity_id
        for entity_id, entity in sorted(world.entities.items())
        if entity.kind == "location"
    ]
    open_obligations = [
        _jsonable(item)
        for item in bundle.social.obligations.values()
        if item.status == "open"
    ]
    open_obligations.sort(key=lambda item: (item["due_tick"], item["obligation_id"]))
    recent_events = [_jsonable(event) for event in bundle.events[-limit:]]

    return {
        "runtime": _runtime_meta(),
        "world": _descriptor_payload(descriptor),
        "snapshot": {
            "timeline_id": timeline,
            "through_sequence": bundle.through_sequence,
            "event_count": len(bundle.events),
            "current_tick": _current_tick(bundle.events),
            "world_hash": world.canonical_hash(),
            "flags": world.flags,
            "entity_count": len(world.entities),
            "actor_count": len(actors),
            "location_count": len(locations),
        },
        "actors": [_actor_probe(bundle, actor_id) for actor_id in actors],
        "social": {
            "directed_bond_count": sum(len(items) for items in bundle.social.bonds_by_actor.values()),
            "obligation_count": len(bundle.social.obligations),
            "open_obligations": open_obligations,
        },
        "diagnostics": _diagnostics(bundle),
        "recent_events": recent_events,
    }


def make_console_handler(database_path: str | Path) -> type[BaseHTTPRequestHandler]:
    legacy_database = Path(database_path)
    catalog = WorldCatalog(legacy_database.parent, legacy_db_path=legacy_database)
    BaseHandler = make_story_console_handler(database_path)

    class Handler(BaseHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path != DEBUG_PREFIX and not parsed.path.startswith(DEBUG_PREFIX + "/"):
                super().do_GET()
                return

            query = parse_qs(parsed.query)
            configured = _debug_token()
            if not configured:
                self._send(HTTPStatus.NOT_FOUND, {"error": "debug api disabled"})
                return
            if len(configured) < 24:
                self._send(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "debug api token is misconfigured"})
                return
            if not _is_authorized(self, query):
                self._send(
                    HTTPStatus.UNAUTHORIZED,
                    {"error": "invalid or missing debug token"},
                    extra_headers={"WWW-Authenticate": 'Bearer realm="WorldOS Debug API"'},
                )
                return

            try:
                self._dispatch_debug_get(parsed.path, query)
            except KeyError as exc:
                self._send(HTTPStatus.NOT_FOUND, {"error": str(exc)})
            except (TypeError, ValueError) as exc:
                self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            except Exception as exc:
                self._send(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

        def _dispatch_debug_get(self, path: str, query: dict[str, list[str]]) -> None:
            if path in {DEBUG_PREFIX, DEBUG_PREFIX + "/", DEBUG_PREFIX + "/health"}:
                worlds = catalog.list_worlds()
                self._send(
                    HTTPStatus.OK,
                    {
                        "ok": True,
                        "read_only": True,
                        "runtime": _runtime_meta(),
                        "world_count": len(worlds),
                        "capabilities": [
                            "worlds",
                            "probe",
                            "overview",
                            "events",
                            "actor",
                            "social",
                            "narrative",
                            "diagnostics",
                            "explain-event",
                        ],
                    },
                )
                return

            if path == DEBUG_PREFIX + "/worlds":
                payload: list[dict[str, Any]] = []
                for descriptor in catalog.list_worlds():
                    item = _descriptor_payload(descriptor)
                    try:
                        with SQLiteEventStore(descriptor.database_path) as store:
                            bundle = WorldInspector(store).bundle("main")
                            item.update(
                                {
                                    "current_tick": _current_tick(bundle.events),
                                    "event_count": len(bundle.events),
                                    "world_hash": bundle.world.canonical_hash(),
                                }
                            )
                    except Exception as exc:
                        item["read_error"] = str(exc)
                    payload.append(item)
                self._send(HTTPStatus.OK, {"runtime": _runtime_meta(), "worlds": payload})
                return

            prefix = DEBUG_PREFIX + "/worlds/"
            if not path.startswith(prefix):
                self._send(HTTPStatus.NOT_FOUND, {"error": "debug endpoint not found"})
                return

            relative = path.removeprefix(prefix).strip("/")
            parts = [unquote(part) for part in relative.split("/") if part]
            if len(parts) < 2:
                self._send(HTTPStatus.NOT_FOUND, {"error": "debug endpoint not found"})
                return

            world_id, action = parts[0], parts[1]
            descriptor = catalog.get(world_id)
            timeline = query.get("timeline", ["main"])[0]
            with SQLiteEventStore(descriptor.database_path) as store:
                inspector = WorldInspector(store)
                service = WebInspectorService(store)

                if action == "probe" and len(parts) == 2:
                    self._send(HTTPStatus.OK, _probe(store, descriptor, timeline, _parse_limit(query, default=50)))
                    return
                if action == "overview" and len(parts) == 2:
                    self._send(HTTPStatus.OK, service.overview(timeline))
                    return
                if action == "diagnostics" and len(parts) == 2:
                    self._send(HTTPStatus.OK, _diagnostics(inspector.bundle(timeline)))
                    return
                if action == "social" and len(parts) == 2:
                    self._send(HTTPStatus.OK, _jsonable(inspector.bundle(timeline).social))
                    return
                if action == "events" and len(parts) == 2:
                    events = inspector.events(
                        timeline,
                        event_type=query.get("event_type", [None])[0],
                        actor_id=query.get("actor_id", [None])[0],
                        subject_id=query.get("subject_id", [None])[0],
                        tick=int(query["tick"][0]) if "tick" in query else None,
                        correlation_id=query.get("correlation_id", [None])[0],
                    )
                    limit = _parse_limit(query)
                    self._send(HTTPStatus.OK, {"events": [_jsonable(event) for event in events[-limit:]], "matched": len(events)})
                    return
                if action == "actor" and len(parts) >= 3:
                    actor_id = "/".join(parts[2:])
                    self._send(HTTPStatus.OK, _jsonable(inspector.actor(actor_id, timeline)))
                    return
                if action == "narrative" and len(parts) == 2:
                    narrator = NarratorReadAPI(inspector)
                    actor_id = query.get("actor", [None])[0]
                    from_sequence = int(query.get("from_sequence", ["1"])[0])
                    self._send(
                        HTTPStatus.OK,
                        _jsonable(
                            narrator.context(
                                timeline,
                                from_sequence=from_sequence,
                                perspective_actor_id=actor_id,
                            )
                        ),
                    )
                    return
                if action == "explain-event" and len(parts) >= 3:
                    event_id = "/".join(parts[2:])
                    explained = inspector.explain_event(event_id, timeline)
                    if explained is None:
                        raise KeyError(f"unknown event: {event_id}")
                    self._send(HTTPStatus.OK, _jsonable(explained))
                    return

            self._send(HTTPStatus.NOT_FOUND, {"error": "debug endpoint not found"})

    return Handler


def serve_world_console(
    database_path: str | Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> None:
    if not 0 < port < 65536:
        raise ValueError("端口必须在 1 到 65535 之间")
    server = ThreadingHTTPServer((host, port), make_console_handler(database_path))
    try:
        server.serve_forever()
    finally:
        server.server_close()
