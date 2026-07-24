from __future__ import annotations

from pydantic import BaseModel, Field

from .events import Event, NewEvent
from .knowledge import KnowledgeProjection, replay_knowledge
from .memory import MemoryEngine, MemoryProjection, replay_memory
from .perception import PerceptionEngine
from .pipeline import IntentPipeline, IntentProcessingResult
from .planning import GoalPlanner, PlannerProjection, PlanningContext, replay_planning
from .store import InMemoryEventStore
from .world import WorldProjection, replay_world


class TickAlreadyCompletedError(RuntimeError):
    pass


class TickResult(BaseModel):
    timeline_id: str
    tick: int
    actors: tuple[str, ...]
    intent_results: tuple[IntentProcessingResult, ...] = ()
    committed_events: tuple[Event, ...] = ()
    phase_counts: dict[str, int] = Field(default_factory=dict)


class DeterministicTickEngine:
    """Runs one replayable world tick through cognition, action, perception and memory."""

    def __init__(self, store: InMemoryEventStore, *, world_seed: str | int, planner: GoalPlanner | None = None, perception: PerceptionEngine | None = None, memory: MemoryEngine | None = None) -> None:
        self.store = store
        self.pipeline = IntentPipeline(store, world_seed=world_seed)
        self.planner = planner or GoalPlanner()
        self.perception = perception or PerceptionEngine()
        self.memory = memory or MemoryEngine()

    def run_tick(self, timeline_id: str, tick: int) -> TickResult:
        if tick < 0:
            raise ValueError("tick must be non-negative")
        history = self.store.read(timeline_id)
        if any(event.tick == tick and event.event_type == "tick.completed" for event in history):
            raise TickAlreadyCompletedError(f"tick already completed: {tick}")

        committed: list[Event] = []
        intent_results: list[IntentProcessingResult] = []
        phase_counts: dict[str, int] = {}
        self._append(timeline_id, [NewEvent(tick=tick, phase="scheduler", event_type="tick.started", payload={"tick": tick})], committed, phase_counts)

        _, planning, _ = self._projections(timeline_id)
        actors = tuple(sorted(owner_id for owner_id in planning.goals_by_owner if planning.active_goals(owner_id)))
        action_events: list[Event] = []

        for actor_id in actors:
            world, planning, memory = self._projections(timeline_id)
            context = PlanningContext(owner_id=actor_id, tick=tick, world=world, memory=memory)
            goal = self.planner.choose_goal(planning, actor_id)
            if goal is None:
                continue
            if not planning.pending_steps(goal.goal_id):
                plan_events = self.planner.plan(goal, context)
                if plan_events:
                    self._append(timeline_id, plan_events, committed, phase_counts)
                    planning = replay_planning(self.store.read(timeline_id))
            intent = self.planner.next_intent(planning, context)
            if intent is None:
                continue
            result = self.pipeline.process(timeline_id, intent, expected_sequence=len(self.store.read(timeline_id)))
            intent_results.append(result)
            committed.extend(result.committed_events)
            for event in result.committed_events:
                phase_counts[event.phase] = phase_counts.get(event.phase, 0) + 1
            action_events.extend(event for event in result.committed_events if event.phase in {"intent", "resolution", "effects"})

            step_id = intent.metadata.get("step_id")
            goal_id = intent.metadata.get("goal_id")
            if step_id and goal_id:
                self._append(timeline_id, [NewEvent(tick=tick, phase="planning", event_type="plan.step_status_changed", actor_id=actor_id, subject_ids=(actor_id,), correlation_id=goal_id, caused_by=tuple(event.event_id for event in result.committed_events), payload={"goal_id": goal_id, "step_id": step_id, "status": "completed" if result.accepted else "failed"})], committed, phase_counts)

        if action_events:
            perception_candidates = self.perception.derive(action_events, replay_world(self.store.read(timeline_id)))
            self._append(timeline_id, perception_candidates, committed, phase_counts)

        knowledge = replay_knowledge(self.store.read(timeline_id))
        memory_candidates = self.memory.derive(self._knowledge_for_tick(knowledge, tick), tick=tick)
        self._append(timeline_id, memory_candidates, committed, phase_counts)

        completion = NewEvent(tick=tick, phase="scheduler", event_type="tick.completed", caused_by=tuple(event.event_id for event in committed), payload={"tick": tick, "actors": list(actors), "accepted_intents": sum(1 for result in intent_results if result.accepted), "rejected_intents": sum(1 for result in intent_results if not result.accepted), "event_count_before_completion": len(committed)})
        self._append(timeline_id, [completion], committed, phase_counts)
        return TickResult(timeline_id=timeline_id, tick=tick, actors=actors, intent_results=tuple(intent_results), committed_events=tuple(committed), phase_counts=phase_counts)

    def _append(self, timeline_id: str, candidates: list[NewEvent], committed: list[Event], phase_counts: dict[str, int]) -> None:
        if not candidates:
            return
        appended = self.store.append_batch(timeline_id, candidates, expected_sequence=len(self.store.read(timeline_id)))
        committed.extend(appended)
        for event in appended:
            phase_counts[event.phase] = phase_counts.get(event.phase, 0) + 1

    def _projections(self, timeline_id: str) -> tuple[WorldProjection, PlannerProjection, MemoryProjection]:
        events = self.store.read(timeline_id)
        return replay_world(events), replay_planning(events), replay_memory(events)

    @staticmethod
    def _knowledge_for_tick(knowledge: KnowledgeProjection, tick: int) -> KnowledgeProjection:
        filtered = KnowledgeProjection()
        for observer_id, beliefs in knowledge.beliefs_by_observer.items():
            selected = {belief_id: belief for belief_id, belief in beliefs.items() if belief.updated_tick == tick}
            if selected:
                filtered.beliefs_by_observer[observer_id] = selected
        return filtered
