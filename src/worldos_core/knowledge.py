from __future__ import annotations

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


KNOWLEDGE_EVENT_TYPES = {"observation.created", "belief.updated"}


def reduce_knowledge(state: KnowledgeProjection, event: Event) -> KnowledgeProjection:
    """Apply a knowledge event with structural sharing.

    Unrelated events return the existing immutable-by-convention projection. Relevant
    events copy only the top-level container and the observer bucket being changed.
    """
    if event.event_type not in KNOWLEDGE_EVENT_TYPES:
        return state

    next_state = state.model_copy(deep=False)
    next_state.applied_event_ids = [*state.applied_event_ids, event.event_id]

    if event.event_type == "observation.created":
        observation = Observation(**event.payload)
        next_state.observations = dict(state.observations)
        next_state.observations[observation.observation_id] = observation
        return next_state

    belief = Belief(**event.payload)
    next_state.beliefs_by_observer = dict(state.beliefs_by_observer)
    observer_beliefs = dict(state.beliefs_by_observer.get(belief.observer_id, {}))
    observer_beliefs[belief.belief_id] = belief
    next_state.beliefs_by_observer[belief.observer_id] = observer_beliefs
    return next_state


def replay_knowledge(events: list[Event], initial: KnowledgeProjection | None = None) -> KnowledgeProjection:
    state = initial.model_copy(deep=True) if initial else KnowledgeProjection()
    for event in events:
        state = reduce_knowledge(state, event)
    return state
