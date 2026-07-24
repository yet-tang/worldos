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
        data = self.model_dump(mode="json", exclude={"applied_event_ids"})
        canonical = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()


Reducer = Callable[[WorldProjection, Event], WorldProjection]


NON_WORLD_EVENTS = {
    "intent.rejected",
    "move.attempted",
    "move.resolved",
    "attack.attempted",
    "attack.resolved",
    "observation.created",
    "belief.updated",
    "memory.recorded",
    "memory.forgotten",
    "goal.created",
    "goal.status_changed",
    "plan.step_created",
    "plan.step_status_changed",
    "tick.started",
    "tick.completed",
}


def reduce_event(state: WorldProjection, event: Event) -> WorldProjection:
    next_state = state.model_copy(deep=True)
    next_state.tick = max(next_state.tick, event.tick)

    if event.event_type in NON_WORLD_EVENTS:
        pass
    elif event.event_type == "world.created":
        next_state.flags.update(event.payload.get("flags", {}))
    elif event.event_type == "entity.created":
        entity_id = _single_subject(event)
        if entity_id in next_state.entities:
            raise ValueError(f"entity already exists: {entity_id}")
        next_state.entities[entity_id] = EntityProjection(entity_id=entity_id, kind=event.payload["kind"], components=deepcopy(event.payload.get("components", {})))
    elif event.event_type == "entity.component_set":
        entity = _entity(next_state, _single_subject(event))
        entity.components[event.payload["component"]] = deepcopy(event.payload["value"])
    elif event.event_type == "entity.moved":
        entity = _entity(next_state, _single_subject(event))
        entity.components["position"] = {"location_id": event.payload["to_location_id"]}
    elif event.event_type == "health.changed":
        entity = _entity(next_state, _single_subject(event))
        health = deepcopy(entity.components.get("health", {"current": 100, "maximum": 100}))
        health["current"] = max(0, min(health["maximum"], health["current"] + event.payload["delta"]))
        entity.components["health"] = health
    elif event.event_type == "entity.deactivated":
        _entity(next_state, _single_subject(event)).active = False
    elif event.event_type == "world.flag_set":
        next_state.flags[event.payload["name"]] = deepcopy(event.payload["value"])
    else:
        raise ValueError(f"no reducer registered for event type: {event.event_type}")

    next_state.applied_event_ids.append(event.event_id)
    return next_state


def replay_world(events: list[Event], initial: WorldProjection | None = None) -> WorldProjection:
    state = initial.model_copy(deep=True) if initial else WorldProjection()
    for expected_sequence, event in enumerate(events, start=1):
        if event.sequence != expected_sequence:
            raise ValueError(f"non-contiguous history at event {event.event_id}: expected sequence {expected_sequence}, got {event.sequence}")
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
