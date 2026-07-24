from __future__ import annotations

from copy import deepcopy
from typing import Any

from pydantic import BaseModel, Field

from .events import Event


class Observation(BaseModel):
    observation_id: str
    observer_id: str
    source_event_id: str
    tick: int
    fact_type: str
    subject_ids: tuple[str, ...] = ()
    data: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 1.0


class Belief(BaseModel):
    belief_id: str
    observer_id: str
    fact_type: str
    subject_ids: tuple[str, ...] = ()
    data: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 1.0
    source_observation_id: str
    updated_tick: int


class KnowledgeProjection(BaseModel):
    observations: dict[str, Observation] = Field(default_factory=dict)
    beliefs_by_observer: dict[str, dict[str, Belief]] = Field(default_factory=dict)
    applied_event_ids: list[str] = Field(default_factory=list)


def reduce_knowledge(state: KnowledgeProjection, event: Event) -> KnowledgeProjection:
    next_state = state.model_copy(deep=True)
    if event.event_type == "observation.created":
        observation = Observation(**event.payload)
        next_state.observations[observation.observation_id] = observation
    elif event.event_type == "belief.updated":
        belief = Belief(**event.payload)
        next_state.beliefs_by_observer.setdefault(belief.observer_id, {})[belief.belief_id] = belief
    else:
        return next_state
    next_state.applied_event_ids.append(event.event_id)
    return next_state


def replay_knowledge(events: list[Event], initial: KnowledgeProjection | None = None) -> KnowledgeProjection:
    state = initial.model_copy(deep=True) if initial else KnowledgeProjection()
    for event in events:
        state = reduce_knowledge(state, event)
    return state
