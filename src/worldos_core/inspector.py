from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .events import Event
from .knowledge import Belief, Observation, replay_knowledge
from .memory import MemoryRecord, replay_memory
from .planning import Goal, PlanStep, replay_planning
from .store import InMemoryEventStore
from .timeline import Timeline
from .world import EntityProjection, WorldProjection, replay_world


class TimelineSnapshot(BaseModel):
    timeline: Timeline
    through_sequence: int
    world: WorldProjection
    event_count: int
    world_hash: str


class ActorDebugView(BaseModel):
    actor_id: str
    entity: EntityProjection | None = None
    observations: list[Observation] = Field(default_factory=list)
    beliefs: list[Belief] = Field(default_factory=list)
    memories: list[MemoryRecord] = Field(default_factory=list)
    goals: list[Goal] = Field(default_factory=list)
    plan_steps: list[PlanStep] = Field(default_factory=list)


class WorldInspector:
    """Read-only, replay-backed debugging facade over one event store."""

    def __init__(self, store: InMemoryEventStore) -> None:
        self._store = store

    def events(
        self,
        timeline_id: str = "main",
        *,
        through_sequence: int | None = None,
        event_type: str | None = None,
        actor_id: str | None = None,
        subject_id: str | None = None,
        tick: int | None = None,
        correlation_id: str | None = None,
    ) -> list[Event]:
        events = self._store.read(timeline_id, through_sequence)
        return [
            event
            for event in events
            if (event_type is None or event.event_type == event_type)
            and (actor_id is None or event.actor_id == actor_id)
            and (subject_id is None or subject_id in event.subject_ids)
            and (tick is None or event.tick == tick)
            and (correlation_id is None or event.correlation_id == correlation_id)
        ]

    def snapshot(self, timeline_id: str = "main", *, through_sequence: int | None = None) -> TimelineSnapshot:
        events = self._store.read(timeline_id, through_sequence)
        world = replay_world(events)
        return TimelineSnapshot(
            timeline=self._store.timeline(timeline_id),
            through_sequence=len(events),
            world=world,
            event_count=len(events),
            world_hash=world.canonical_hash(),
        )

    def entity(self, entity_id: str, timeline_id: str = "main", *, through_sequence: int | None = None) -> EntityProjection | None:
        return self.snapshot(timeline_id, through_sequence=through_sequence).world.entities.get(entity_id)

    def actor(self, actor_id: str, timeline_id: str = "main", *, through_sequence: int | None = None) -> ActorDebugView:
        events = self._store.read(timeline_id, through_sequence)
        world = replay_world(events)
        knowledge = replay_knowledge(events)
        memory = replay_memory(events)
        planning = replay_planning(events)

        observations = sorted(
            [item for item in knowledge.observations.values() if item.observer_id == actor_id],
            key=lambda item: (item.tick, item.observation_id),
        )
        beliefs = sorted(
            knowledge.beliefs_by_observer.get(actor_id, {}).values(),
            key=lambda item: (item.updated_tick, item.belief_id),
        )
        memories = memory.memories(actor_id)
        goals = sorted(
            planning.goals_by_owner.get(actor_id, {}).values(),
            key=lambda item: (-item.priority, item.created_tick, item.goal_id),
        )
        goal_ids = {goal.goal_id for goal in goals}
        steps = sorted(
            [step for goal_id in goal_ids for step in planning.steps_by_goal.get(goal_id, {}).values()],
            key=lambda item: (item.goal_id, item.ordinal, item.step_id),
        )
        return ActorDebugView(
            actor_id=actor_id,
            entity=world.entities.get(actor_id),
            observations=observations,
            beliefs=beliefs,
            memories=memories,
            goals=goals,
            plan_steps=steps,
        )

    def explain_event(self, event_id: str, timeline_id: str = "main") -> dict[str, Any] | None:
        by_id = {event.event_id: event for event in self._store.read(timeline_id)}
        event = by_id.get(event_id)
        if event is None:
            return None
        causes = [by_id[cause] for cause in event.caused_by if cause in by_id]
        consequences = [candidate for candidate in by_id.values() if event_id in candidate.caused_by]
        return {
            "event": event,
            "causes": sorted(causes, key=lambda item: item.sequence),
            "consequences": sorted(consequences, key=lambda item: item.sequence),
        }
