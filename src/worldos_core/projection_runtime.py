from __future__ import annotations

from copy import deepcopy

from .events import Event
from .knowledge import Belief, KnowledgeProjection, Observation
from .memory import MemoryPolicy, MemoryProjection, MemoryRecord
from .planning import Goal, PlanStep, PlannerProjection
from .world import EntityProjection, NON_WORLD_EVENTS, WorldProjection


PLANNING_EVENTS = {
    "goal.created",
    "goal.status_changed",
    "plan.step_created",
    "plan.step_status_changed",
}
MEMORY_EVENTS = {"memory.recorded", "memory.forgotten"}
KNOWLEDGE_EVENTS = {"observation.created", "belief.updated"}


def apply_world_in_place(state: WorldProjection, event: Event) -> None:
    """Apply one event to a private cached world projection without copying it."""
    state.tick = max(state.tick, event.tick)
    if event.event_type in NON_WORLD_EVENTS:
        return
    if event.event_type == "world.created":
        state.flags.update(deepcopy(event.payload.get("flags", {})))
    elif event.event_type == "entity.created":
        entity_id = _single_subject(event)
        if entity_id in state.entities:
            raise ValueError(f"entity already exists: {entity_id}")
        state.entities[entity_id] = EntityProjection(
            entity_id=entity_id,
            kind=event.payload["kind"],
            components=deepcopy(event.payload.get("components", {})),
        )
    elif event.event_type == "entity.component_set":
        entity = _entity(state, _single_subject(event))
        entity.components[event.payload["component"]] = deepcopy(event.payload["value"])
    elif event.event_type == "entity.component_removed":
        _entity(state, _single_subject(event)).components.pop(event.payload["component"], None)
    elif event.event_type == "entity.moved":
        _entity(state, _single_subject(event)).components["position"] = {
            "location_id": event.payload["to_location_id"]
        }
    elif event.event_type == "health.changed":
        entity = _entity(state, _single_subject(event))
        health = deepcopy(entity.components.get("health", {"current": 100, "maximum": 100}))
        health["current"] = max(
            0,
            min(health["maximum"], health["current"] + event.payload["delta"]),
        )
        entity.components["health"] = health
    elif event.event_type == "entity.deactivated":
        _entity(state, _single_subject(event)).active = False
    elif event.event_type == "world.flag_set":
        state.flags[event.payload["name"]] = deepcopy(event.payload["value"])
    else:
        raise ValueError(f"no reducer registered for event type: {event.event_type}")
    # Track only events that actually participate in this projection. Keeping every
    # timeline event ID here made replay itself quadratic without adding world state.
    state.applied_event_ids.append(event.event_id)


def apply_planning_in_place(state: PlannerProjection, event: Event) -> None:
    if event.event_type not in PLANNING_EVENTS:
        return
    if event.event_type == "goal.created":
        goal = Goal(**event.payload)
        state.goals_by_owner.setdefault(goal.owner_id, {})[goal.goal_id] = goal
    elif event.event_type == "goal.status_changed":
        state.goals_by_owner[event.payload["owner_id"]][event.payload["goal_id"]].status = event.payload["status"]
    elif event.event_type == "plan.step_created":
        step = PlanStep(**event.payload)
        state.steps_by_goal.setdefault(step.goal_id, {})[step.step_id] = step
    else:
        state.steps_by_goal[event.payload["goal_id"]][event.payload["step_id"]].status = event.payload["status"]
    state.applied_event_ids.append(event.event_id)


def apply_memory_in_place(
    state: MemoryProjection,
    event: Event,
    policy: MemoryPolicy | None = None,
) -> None:
    if event.event_type not in MEMORY_EVENTS:
        return
    active_policy = policy or MemoryPolicy()
    if event.event_type == "memory.recorded":
        record = MemoryRecord(**event.payload)
        owner_records = state.records_by_owner.setdefault(record.owner_id, {})
        owner_records[record.memory_id] = record
        if record.kind == "working":
            order = state.working_order.setdefault(record.owner_id, [])
            if record.memory_id in order:
                order.remove(record.memory_id)
            order.append(record.memory_id)
            while len(order) > active_policy.working_capacity:
                expired_id = order.pop(0)
                if expired_id in owner_records:
                    owner_records[expired_id].active = False
    else:
        record = state.records_by_owner.get(event.payload["owner_id"], {}).get(event.payload["memory_id"])
        if record is not None:
            record.active = False
    state.applied_event_ids.append(event.event_id)


def apply_knowledge_in_place(state: KnowledgeProjection, event: Event) -> None:
    if event.event_type not in KNOWLEDGE_EVENTS:
        return
    if event.event_type == "observation.created":
        observation = Observation(**event.payload)
        state.observations[observation.observation_id] = observation
    else:
        belief = Belief(**event.payload)
        state.beliefs_by_observer.setdefault(belief.observer_id, {})[belief.belief_id] = belief
    state.applied_event_ids.append(event.event_id)


def _single_subject(event: Event) -> str:
    if len(event.subject_ids) != 1:
        raise ValueError(f"{event.event_type} requires exactly one subject")
    return event.subject_ids[0]


def _entity(state: WorldProjection, entity_id: str) -> EntityProjection:
    try:
        return state.entities[entity_id]
    except KeyError as exc:
        raise ValueError(f"unknown entity: {entity_id}") from exc
