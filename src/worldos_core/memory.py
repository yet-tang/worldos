from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from typing import Any, Literal

from pydantic import BaseModel, Field

from .events import Event, NewEvent
from .knowledge import KnowledgeProjection

MemoryKind = Literal["working", "episodic", "semantic", "identity"]


class MemoryRecord(BaseModel):
    memory_id: str
    owner_id: str
    kind: MemoryKind
    tick: int
    content: dict[str, Any] = Field(default_factory=dict)
    source_ids: tuple[str, ...] = ()
    confidence: float = 1.0
    salience: float = 0.5
    active: bool = True


class MemoryProjection(BaseModel):
    records_by_owner: dict[str, dict[str, MemoryRecord]] = Field(default_factory=dict)
    working_order: dict[str, list[str]] = Field(default_factory=dict)
    applied_event_ids: list[str] = Field(default_factory=list)

    def memories(self, owner_id: str, kind: MemoryKind | None = None) -> list[MemoryRecord]:
        records = self.records_by_owner.get(owner_id, {}).values()
        result = [record for record in records if record.active and (kind is None or record.kind == kind)]
        return sorted(result, key=lambda record: (record.tick, record.memory_id))


class MemoryPolicy(BaseModel):
    working_capacity: int = 7
    episodic_confidence_threshold: float = 0.5
    semantic_confidence_threshold: float = 0.8
    identity_fact_types: tuple[str, ...] = ("identity", "role", "affiliation")


class MemoryEngine:
    """Deterministically converts knowledge into explicit memory events."""

    def __init__(self, policy: MemoryPolicy | None = None) -> None:
        self.policy = policy or MemoryPolicy()

    def derive(self, knowledge: KnowledgeProjection, *, tick: int) -> list[NewEvent]:
        events: list[NewEvent] = []
        for owner_id in sorted(knowledge.beliefs_by_observer):
            beliefs = knowledge.beliefs_by_observer[owner_id]
            for belief_id in sorted(beliefs):
                belief = beliefs[belief_id]
                working_id = f"mem_working_{belief.belief_id}"
                events.append(self._event(owner_id, working_id, "working", tick, belief.model_dump(mode="json"), (belief.belief_id,), belief.confidence, 0.5))
                if belief.confidence >= self.policy.episodic_confidence_threshold:
                    episodic_id = f"mem_episode_{belief.belief_id}"
                    events.append(self._event(owner_id, episodic_id, "episodic", tick, belief.model_dump(mode="json"), (belief.belief_id,), belief.confidence, 0.7))
                if belief.confidence >= self.policy.semantic_confidence_threshold:
                    semantic_id = f"mem_semantic_{owner_id}_{belief.fact_type}_{'_'.join(belief.subject_ids) or 'world'}"
                    events.append(self._event(owner_id, semantic_id, "semantic", tick, belief.model_dump(mode="json"), (belief.belief_id,), belief.confidence, 0.8))
                if belief.fact_type in self.policy.identity_fact_types:
                    identity_id = f"mem_identity_{owner_id}_{belief.fact_type}"
                    events.append(self._event(owner_id, identity_id, "identity", tick, belief.model_dump(mode="json"), (belief.belief_id,), belief.confidence, 1.0))
        return events

    @staticmethod
    def _event(owner_id: str, memory_id: str, kind: MemoryKind, tick: int, content: dict[str, Any], source_ids: tuple[str, ...], confidence: float, salience: float) -> NewEvent:
        return NewEvent(
            tick=tick,
            phase="memory",
            event_type="memory.recorded",
            actor_id=owner_id,
            subject_ids=(owner_id,),
            payload={
                "memory_id": memory_id,
                "owner_id": owner_id,
                "kind": kind,
                "tick": tick,
                "content": deepcopy(content),
                "source_ids": source_ids,
                "confidence": confidence,
                "salience": salience,
                "active": True,
            },
        )


def reduce_memory(state: MemoryProjection, event: Event, policy: MemoryPolicy | None = None) -> MemoryProjection:
    next_state = state.model_copy(deep=True)
    active_policy = policy or MemoryPolicy()
    if event.event_type == "memory.recorded":
        record = MemoryRecord(**event.payload)
        owner_records = next_state.records_by_owner.setdefault(record.owner_id, {})
        owner_records[record.memory_id] = record
        if record.kind == "working":
            order = next_state.working_order.setdefault(record.owner_id, [])
            if record.memory_id in order:
                order.remove(record.memory_id)
            order.append(record.memory_id)
            while len(order) > active_policy.working_capacity:
                expired_id = order.pop(0)
                if expired_id in owner_records:
                    owner_records[expired_id].active = False
    elif event.event_type == "memory.forgotten":
        owner_id = event.payload["owner_id"]
        memory_id = event.payload["memory_id"]
        record = next_state.records_by_owner.get(owner_id, {}).get(memory_id)
        if record is not None:
            record.active = False
    else:
        return next_state
    next_state.applied_event_ids.append(event.event_id)
    return next_state


def replay_memory(events: list[Event], initial: MemoryProjection | None = None, policy: MemoryPolicy | None = None) -> MemoryProjection:
    state = initial.model_copy(deep=True) if initial else MemoryProjection()
    for event in events:
        state = reduce_memory(state, event, policy)
    return state
