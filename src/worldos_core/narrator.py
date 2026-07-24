from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from .events import Event
from .inspector import WorldInspector
from .knowledge import Belief, Observation
from .memory import MemoryRecord
from .planning import Goal, PlanStep


class NarrativeEvent(BaseModel):
    event_id: str
    sequence: int
    tick: int
    phase: str
    event_type: str
    actor_id: str | None = None
    subject_ids: tuple[str, ...] = ()
    payload: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_event(cls, event: Event) -> "NarrativeEvent":
        return cls(
            event_id=event.event_id,
            sequence=event.sequence,
            tick=event.tick,
            phase=event.phase,
            event_type=event.event_type,
            actor_id=event.actor_id,
            subject_ids=event.subject_ids,
            payload=event.payload,
        )


class NarrativeContext(BaseModel):
    timeline_id: str
    through_sequence: int
    mode: Literal["omniscient", "actor"]
    perspective_actor_id: str | None = None
    world_hash: str | None = None
    events: list[NarrativeEvent] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)
    beliefs: list[Belief] = Field(default_factory=list)
    memories: list[MemoryRecord] = Field(default_factory=list)
    goals: list[Goal] = Field(default_factory=list)
    plan_steps: list[PlanStep] = Field(default_factory=list)


class NarratorReadAPI:
    """Builds deterministic, read-only narrative material from WorldInspector."""

    def __init__(self, inspector: WorldInspector) -> None:
        self._inspector = inspector

    def context(
        self,
        timeline_id: str = "main",
        *,
        through_sequence: int | None = None,
        from_sequence: int = 1,
        perspective_actor_id: str | None = None,
    ) -> NarrativeContext:
        if from_sequence < 1:
            raise ValueError("from_sequence must be at least 1")

        snapshot = self._inspector.snapshot(timeline_id, through_sequence=through_sequence)
        visible_events = [
            event
            for event in self._inspector.events(timeline_id, through_sequence=through_sequence)
            if event.sequence >= from_sequence
        ]

        if perspective_actor_id is None:
            return NarrativeContext(
                timeline_id=timeline_id,
                through_sequence=snapshot.through_sequence,
                mode="omniscient",
                world_hash=snapshot.world_hash,
                events=[NarrativeEvent.from_event(event) for event in visible_events],
            )

        actor = self._inspector.actor(
            perspective_actor_id,
            timeline_id,
            through_sequence=through_sequence,
        )
        observed_source_ids = {
            observation.source_event_id
            for observation in actor.observations
            if observation.source_event_id
        }
        actor_visible_events = [
            event
            for event in visible_events
            if event.event_id in observed_source_ids
        ]

        return NarrativeContext(
            timeline_id=timeline_id,
            through_sequence=snapshot.through_sequence,
            mode="actor",
            perspective_actor_id=perspective_actor_id,
            world_hash=None,
            events=[NarrativeEvent.from_event(event) for event in actor_visible_events],
            observations=actor.observations,
            beliefs=actor.beliefs,
            memories=actor.memories,
            goals=actor.goals,
            plan_steps=actor.plan_steps,
        )
