from __future__ import annotations

from collections import Counter
import os
from pathlib import Path
from typing import Any

from .inspector import WorldInspector
from .narrator import NarratorReadAPI
from .sqlite_store import SQLiteEventStore
from .web_inspector import WebInspectorService, _jsonable
from .world_creator import WorldCatalog, WorldDescriptor


MAX_EVENT_LIMIT = 1000
DEFAULT_EVENT_LIMIT = 100


def runtime_meta() -> dict[str, str]:
    return {
        "vcs_ref": os.environ.get("WORLDOS_VCS_REF", "unknown"),
        "version": os.environ.get("WORLDOS_VERSION", "dev"),
    }


def descriptor_payload(descriptor: WorldDescriptor) -> dict[str, Any]:
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


def current_tick(events: list[Any]) -> int:
    completed = [event.tick for event in events if event.event_type == "tick.completed"]
    if completed:
        return max(completed)
    return max((event.tick for event in events), default=0)


def actor_name(entity_id: str, world: Any) -> str:
    entity = world.entities.get(entity_id)
    if entity is None:
        return entity_id
    identity = entity.components.get("identity", {})
    if isinstance(identity, dict):
        return str(identity.get("name") or entity_id)
    return entity_id


def diagnostics(bundle: Any) -> dict[str, Any]:
    events = bundle.events
    world = bundle.world
    planning = bundle.planning
    social = bundle.social
    tick = current_tick(events)

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

    incomplete_ticks = sorted(item for item, count in started.items() if count > completed.get(item, 0))
    duplicate_completed_ticks = sorted(item for item, count in completed.items() if count > 1)

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
        if item.status == "open" and item.due_tick <= tick
    ]
    overdue_obligations.sort(key=lambda item: (item["due_tick"], item["obligation_id"]))

    stalled_active_goals: list[dict[str, Any]] = []
    for owner_id, goals in sorted(planning.goals_by_owner.items()):
        for goal in sorted(goals.values(), key=lambda item: item.goal_id):
            if goal.status != "active" or goal.created_tick >= tick:
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


def actor_probe(bundle: Any, actor_id: str) -> dict[str, Any]:
    entity = bundle.world.entities[actor_id]
    components = entity.components
    active_goals = list(bundle.planning.active_goals(actor_id))
    bonds = list(bundle.social.bonds_by_actor.get(actor_id, {}).values())
    bonds.sort(key=lambda item: (-item.trust, -item.affinity, item.other_id))
    return {
        "actor_id": actor_id,
        "name": actor_name(actor_id, bundle.world),
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
            {**_jsonable(bond), "label": bond.label(), "other_name": actor_name(bond.other_id, bundle.world)}
            for bond in bonds
        ],
        "obligations_as_debtor": [_jsonable(item) for item in bundle.social.open_obligations_for_debtor(actor_id)],
        "obligations_as_creditor": [_jsonable(item) for item in bundle.social.open_obligations_for_creditor(actor_id)],
    }


class WorldReadService:
    """Semantic, transport-neutral read service for engineering agents and UIs."""

    def __init__(self, database_path: str | Path) -> None:
        legacy_database = Path(database_path)
        self.catalog = WorldCatalog(legacy_database.parent, legacy_db_path=legacy_database)

    def health(self) -> dict[str, Any]:
        return {
            "ok": True,
            "read_only": True,
            "runtime": runtime_meta(),
            "world_count": len(self.catalog.list_worlds()),
            "capabilities": ["worlds", "probe", "overview", "events", "actor", "social", "narrative", "diagnostics", "explain-event"],
        }

    def list_worlds(self) -> dict[str, Any]:
        payload: list[dict[str, Any]] = []
        for descriptor in self.catalog.list_worlds():
            item = descriptor_payload(descriptor)
            try:
                with SQLiteEventStore(descriptor.database_path) as store:
                    bundle = WorldInspector(store).bundle("main")
                    item.update(
                        {
                            "current_tick": current_tick(bundle.events),
                            "event_count": len(bundle.events),
                            "world_hash": bundle.world.canonical_hash(),
                        }
                    )
            except Exception as exc:
                item["read_error"] = str(exc)
            payload.append(item)
        return {"runtime": runtime_meta(), "worlds": payload}

    def probe_world(self, world_id: str, *, timeline: str = "main", limit: int = 50) -> dict[str, Any]:
        if limit < 1 or limit > MAX_EVENT_LIMIT:
            raise ValueError(f"limit must be between 1 and {MAX_EVENT_LIMIT}")
        descriptor = self.catalog.get(world_id)
        with SQLiteEventStore(descriptor.database_path) as store:
            bundle = WorldInspector(store).bundle(timeline)
            actors = [
                entity_id for entity_id, entity in sorted(bundle.world.entities.items())
                if entity.kind in {"human", "character"}
            ]
            locations = [
                entity_id for entity_id, entity in sorted(bundle.world.entities.items())
                if entity.kind == "location"
            ]
            open_obligations = [
                _jsonable(item) for item in bundle.social.obligations.values() if item.status == "open"
            ]
            open_obligations.sort(key=lambda item: (item["due_tick"], item["obligation_id"]))
            return {
                "runtime": runtime_meta(),
                "world": descriptor_payload(descriptor),
                "snapshot": {
                    "timeline_id": timeline,
                    "through_sequence": bundle.through_sequence,
                    "event_count": len(bundle.events),
                    "current_tick": current_tick(bundle.events),
                    "world_hash": bundle.world.canonical_hash(),
                    "flags": bundle.world.flags,
                    "entity_count": len(bundle.world.entities),
                    "actor_count": len(actors),
                    "location_count": len(locations),
                },
                "actors": [actor_probe(bundle, actor_id) for actor_id in actors],
                "social": {
                    "directed_bond_count": sum(len(items) for items in bundle.social.bonds_by_actor.values()),
                    "obligation_count": len(bundle.social.obligations),
                    "open_obligations": open_obligations,
                },
                "diagnostics": diagnostics(bundle),
                "recent_events": [_jsonable(event) for event in bundle.events[-limit:]],
            }

    def inspect_actor(self, world_id: str, actor_id: str, *, timeline: str = "main") -> dict[str, Any]:
        descriptor = self.catalog.get(world_id)
        with SQLiteEventStore(descriptor.database_path) as store:
            return _jsonable(WorldInspector(store).actor(actor_id, timeline))

    def query_events(
        self,
        world_id: str,
        *,
        timeline: str = "main",
        event_type: str | None = None,
        actor_id: str | None = None,
        subject_id: str | None = None,
        tick: int | None = None,
        correlation_id: str | None = None,
        limit: int = DEFAULT_EVENT_LIMIT,
    ) -> dict[str, Any]:
        if limit < 1 or limit > MAX_EVENT_LIMIT:
            raise ValueError(f"limit must be between 1 and {MAX_EVENT_LIMIT}")
        descriptor = self.catalog.get(world_id)
        with SQLiteEventStore(descriptor.database_path) as store:
            events = WorldInspector(store).events(
                timeline,
                event_type=event_type,
                actor_id=actor_id,
                subject_id=subject_id,
                tick=tick,
                correlation_id=correlation_id,
            )
            return {"events": [_jsonable(event) for event in events[-limit:]], "matched": len(events)}

    def inspect_social_graph(self, world_id: str, *, timeline: str = "main") -> dict[str, Any]:
        descriptor = self.catalog.get(world_id)
        with SQLiteEventStore(descriptor.database_path) as store:
            return _jsonable(WorldInspector(store).bundle(timeline).social)

    def get_narrative_context(
        self,
        world_id: str,
        *,
        timeline: str = "main",
        actor_id: str | None = None,
        from_sequence: int = 1,
    ) -> dict[str, Any]:
        descriptor = self.catalog.get(world_id)
        with SQLiteEventStore(descriptor.database_path) as store:
            narrator = NarratorReadAPI(WorldInspector(store))
            return _jsonable(
                narrator.context(
                    timeline,
                    from_sequence=from_sequence,
                    perspective_actor_id=actor_id,
                )
            )

    def get_diagnostics(self, world_id: str, *, timeline: str = "main") -> dict[str, Any]:
        descriptor = self.catalog.get(world_id)
        with SQLiteEventStore(descriptor.database_path) as store:
            return diagnostics(WorldInspector(store).bundle(timeline))

    def overview(self, world_id: str, *, timeline: str = "main") -> dict[str, Any]:
        descriptor = self.catalog.get(world_id)
        with SQLiteEventStore(descriptor.database_path) as store:
            return WebInspectorService(store).overview(timeline)

    def explain_event(self, world_id: str, event_id: str, *, timeline: str = "main") -> dict[str, Any]:
        descriptor = self.catalog.get(world_id)
        with SQLiteEventStore(descriptor.database_path) as store:
            explained = WorldInspector(store).explain_event(event_id, timeline)
            if explained is None:
                raise KeyError(f"unknown event: {event_id}")
            return _jsonable(explained)
