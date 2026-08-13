from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Any, Callable

from pydantic import BaseModel, Field

from .events import Event


class EntityProjection(BaseModel):
    entity_id: str
    kind: str
    components: dict[str, Any] = Field(default_factory=dict)
    active: bool = True


class WorldProjection(BaseModel):
    tick: int = 0
    entities: dict[str, EntityProjection] = Field(default_factory=dict)
    flags: dict[str, Any] = Field(default_factory=dict)
    applied_event_ids: list[str] = Field(default_factory=list)

    def canonical_hash(self) -> str:
        data = self.model_dump(mode="json", exclude={"tick", "applied_event_ids"})
        canonical = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()


Reducer = Callable[[WorldProjection, Event], WorldProjection]


NON_WORLD_EVENTS = {
    "intent.rejected",
    "move.attempted",
    "move.resolved",
    "attack.attempted",
    "attack.resolved",
    "eat.attempted",
    "eat.resolved",
    "rest.attempted",
    "rest.resolved",
    "social.interacted",
    "social.rumor_shared",
    "social.helped",
    "social.requested",
    "social.request_resolved",
    "social.confronted",
    "social.repaid",
    "obligation.created",
    "obligation.fulfilled",
    "obligation.defaulted",
    "motivation.considered",
    "motivation.selected",
    "observation.created",
    "belief.updated",
    "memory.recorded",
    "memory.forgotten",
    "need.assessed",
    "goal.created",
    "goal.status_changed",
    "plan.step_created",
    "plan.step_status_changed",
    "tick.started",
    "tick.completed",
    "survival.metabolized",
    "resource.produced",
    "trade.completed",
    "rumor.spread",
    "conflict.resolved",
    "runner.paused",
    "runner.resumed",
    "runner.recovered",
}

_WORLD_EVENT_TYPES = {
    "world.created",
    "entity.created",
    "entity.component_set",
    "entity.component_removed",
    "entity.moved",
    "health.changed",
    "entity.deactivated",
    "world.flag_set",
    "experiment.physical_state_override",
}


def reduce_event(state: WorldProjection, event: Event) -> WorldProjection:
    # Event streams are shared by multiple projections and may contain extension or
    # stimulus events that the world projection does not own. Such events must be
    # projection-neutral rather than making the entire history unreplayable. This
    # is the same structural-sharing behavior used by the knowledge/memory/social
    # reducers for unrelated events.
    if event.event_type in NON_WORLD_EVENTS or event.event_type not in _WORLD_EVENT_TYPES:
        if event.tick <= state.tick:
            return state
        return state.model_copy(update={"tick": event.tick})

    next_tick = max(state.tick, event.tick)
    next_applied = [*state.applied_event_ids, event.event_id]

    if event.event_type == "world.created":
        flags = dict(state.flags)
        flags.update(deepcopy(event.payload.get("flags", {})))
        return state.model_copy(update={"tick": next_tick, "flags": flags, "applied_event_ids": next_applied})

    if event.event_type == "world.flag_set":
        flags = dict(state.flags)
        flags[event.payload["name"]] = deepcopy(event.payload["value"])
        return state.model_copy(update={"tick": next_tick, "flags": flags, "applied_event_ids": next_applied})

    if event.event_type == "experiment.physical_state_override":
        overrides = event.payload.get("actors")
        if not isinstance(overrides, list):
            raise ValueError("experiment.physical_state_override requires actors list")
        component_names = {str(item) for item in event.payload.get("component_names", [])}
        entities = dict(state.entities)
        for actor_payload in overrides:
            if not isinstance(actor_payload, dict):
                raise ValueError("physical override actor entry must be an object")
            actor_id = str(actor_payload.get("actor_id") or "").strip()
            if not actor_id:
                raise ValueError("physical override actor_id is required")
            current = _entity(state, actor_id)
            if current.kind != "character":
                raise ValueError(f"physical override requires character entity: {actor_id}")
            desired = actor_payload.get("components", {})
            if not isinstance(desired, dict):
                raise ValueError("physical override components must be an object")
            components = dict(current.components)
            for component in sorted(component_names):
                if component in desired:
                    components[component] = deepcopy(desired[component])
                else:
                    components.pop(component, None)
            entities[actor_id] = current.model_copy(update={"components": components})
        return state.model_copy(update={"tick": next_tick, "entities": entities, "applied_event_ids": next_applied})

    entity_id = _single_subject(event)
    entities = dict(state.entities)

    if event.event_type == "entity.created":
        if entity_id in entities:
            raise ValueError(f"entity already exists: {entity_id}")
        entities[entity_id] = EntityProjection(
            entity_id=entity_id,
            kind=event.payload["kind"],
            components=deepcopy(event.payload.get("components", {})),
        )
        return state.model_copy(update={"tick": next_tick, "entities": entities, "applied_event_ids": next_applied})

    current = _entity(state, entity_id)
    if event.event_type == "entity.deactivated":
        updated = current.model_copy(update={"active": False})
    else:
        components = dict(current.components)
        if event.event_type == "entity.component_set":
            components[event.payload["component"]] = deepcopy(event.payload["value"])
        elif event.event_type == "entity.component_removed":
            components.pop(event.payload["component"], None)
        elif event.event_type == "entity.moved":
            components["position"] = {"location_id": event.payload["to_location_id"]}
        elif event.event_type == "health.changed":
            health = deepcopy(components.get("health", {"current": 100, "maximum": 100}))
            health["current"] = max(0, min(health["maximum"], health["current"] + event.payload["delta"]))
            components["health"] = health
        else:
            raise ValueError(f"no reducer registered for event type: {event.event_type}")
        updated = current.model_copy(update={"components": components})

    entities[entity_id] = updated
    return state.model_copy(update={"tick": next_tick, "entities": entities, "applied_event_ids": next_applied})


def replay_world(events: list[Event], initial: WorldProjection | None = None) -> WorldProjection:
    state = initial.model_copy(deep=True) if initial else WorldProjection()
    for expected_sequence, event in enumerate(events, start=1):
        if event.sequence != expected_sequence:
            raise ValueError(
                f"non-contiguous history at event {event.event_id}: "
                f"expected sequence {expected_sequence}, got {event.sequence}"
            )
        state = reduce_event(state, event)
    return state


def _single_subject(event: Event) -> str:
    if len(event.subject_ids) != 1:
        raise ValueError(f"{event.event_type} requires exactly one subject")
    return event.subject_ids[0]


def _entity(state: WorldProjection, entity_id: str) -> EntityProjection:
    try:
        return state.entities[entity_id]
    except KeyError as exc:
        raise ValueError(f"unknown entity: {entity_id}") from exc
