from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field

from .events import Event, NewEvent
from .knowledge import KnowledgeProjection, replay_knowledge
from .memory import MemoryEngine, MemoryProjection, replay_memory
from .modules import ModuleContext, WorldModule, WorldModuleRegistry
from .needs import NeedEngine
from .perception import PerceptionEngine
from .pipeline import IntentPipeline, IntentProcessingResult
from .planning import GoalPlanner, PlannerProjection, PlanningContext, replay_planning
from .projection_runtime import (
    apply_knowledge_in_place,
    apply_memory_in_place,
    apply_planning_in_place,
    apply_world_in_place,
)
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


@dataclass
class _ProjectionCache:
    history: list[Event]
    world: WorldProjection
    planning: PlannerProjection
    memory: MemoryProjection
    knowledge: KnowledgeProjection


class DeterministicTickEngine:
    """Runs replayable ticks while incrementally maintaining projection state."""

    def __init__(
        self,
        store: InMemoryEventStore,
        *,
        world_seed: str | int,
        planner: GoalPlanner | None = None,
        perception: PerceptionEngine | None = None,
        memory: MemoryEngine | None = None,
        needs: NeedEngine | None = None,
        modules: tuple[WorldModule, ...] = (),
    ) -> None:
        self.store = store
        self.pipeline = IntentPipeline(store, world_seed=world_seed)
        self.planner = planner or GoalPlanner()
        self.perception = perception or PerceptionEngine()
        self.memory = memory or MemoryEngine()
        self.needs = needs or NeedEngine()
        self.modules = WorldModuleRegistry(modules)
        self._projection_caches: dict[str, _ProjectionCache] = {}

    def run_tick(self, timeline_id: str, tick: int) -> TickResult:
        begin = getattr(self.store, "begin_buffer", None)
        commit = getattr(self.store, "commit_buffer", None)
        rollback = getattr(self.store, "rollback_buffer", None)
        if not callable(begin) or not callable(commit) or not callable(rollback):
            return self._run_tick(timeline_id, tick)

        begin(timeline_id)
        try:
            result = self._run_tick(timeline_id, tick)
            commit(timeline_id)
            return result
        except BaseException:
            rollback(timeline_id)
            self.invalidate_cache(timeline_id)
            raise

    def _run_tick(self, timeline_id: str, tick: int) -> TickResult:
        if tick < 0:
            raise ValueError("tick must be non-negative")
        cache = self._cache(timeline_id)
        if any(event.tick == tick and event.event_type == "tick.completed" for event in cache.history):
            raise TickAlreadyCompletedError(f"tick already completed: {tick}")

        committed: list[Event] = []
        intent_results: list[IntentProcessingResult] = []
        phase_counts: dict[str, int] = {}
        self._append(
            cache,
            timeline_id,
            [NewEvent(tick=tick, phase="scheduler", event_type="tick.started", payload={"tick": tick})],
            committed,
            phase_counts,
        )

        pre_context = ModuleContext(
            timeline_id=timeline_id,
            tick=tick,
            world=cache.world,
            history=tuple(cache.history),
        )
        perception_state = cache.world.model_copy(deep=True)
        self._append(
            cache,
            timeline_id,
            self.modules.before_actions(pre_context),
            committed,
            phase_counts,
        )
        self._append(
            cache,
            timeline_id,
            self.needs.derive(cache.world, cache.planning, tick=tick),
            committed,
            phase_counts,
        )
        actors = tuple(
            sorted(
                owner_id
                for owner_id in cache.planning.goals_by_owner
                if cache.planning.active_goals(owner_id)
            )
        )
        action_events: list[Event] = []

        for actor_id in actors:
            context = PlanningContext(
                owner_id=actor_id,
                tick=tick,
                world=cache.world,
                memory=cache.memory,
            )
            goal = self.planner.choose_goal(cache.planning, actor_id)
            if goal is None:
                continue
            if not cache.planning.pending_steps(goal.goal_id):
                self._append(
                    cache,
                    timeline_id,
                    self.planner.plan(goal, context),
                    committed,
                    phase_counts,
                )
            intent = self.planner.next_intent(cache.planning, context)
            if intent is None:
                continue
            result = self.pipeline.process(
                timeline_id,
                intent,
                expected_sequence=len(cache.history),
                state=cache.world,
            )
            intent_results.append(result)
            self._apply_committed(cache, list(result.committed_events), committed, phase_counts)
            action_events.extend(
                event
                for event in result.committed_events
                if event.phase in {"intent", "resolution", "effects"}
            )

            step_id = intent.metadata.get("step_id")
            goal_id = intent.metadata.get("goal_id")
            if step_id and goal_id:
                self._append(
                    cache,
                    timeline_id,
                    [
                        NewEvent(
                            tick=tick,
                            phase="planning",
                            event_type="plan.step_status_changed",
                            actor_id=actor_id,
                            subject_ids=(actor_id,),
                            correlation_id=goal_id,
                            caused_by=tuple(event.event_id for event in result.committed_events),
                            payload={
                                "goal_id": goal_id,
                                "step_id": step_id,
                                "status": "completed" if result.accepted else "failed",
                            },
                        )
                    ],
                    committed,
                    phase_counts,
                )

        post_context = ModuleContext(
            timeline_id=timeline_id,
            tick=tick,
            world=cache.world,
            history=tuple(cache.history),
        )
        self._append(
            cache,
            timeline_id,
            self.modules.after_actions(post_context, tuple(action_events)),
            committed,
            phase_counts,
        )
        action_events.extend(
            event for event in committed if event.tick == tick and event.phase == "module"
        )

        if action_events:
            self._append(
                cache,
                timeline_id,
                self.perception.derive(action_events, perception_state),
                committed,
                phase_counts,
            )

        self._append(
            cache,
            timeline_id,
            self.memory.derive(self._knowledge_for_tick(cache.knowledge, tick), tick=tick),
            committed,
            phase_counts,
        )

        completion = NewEvent(
            tick=tick,
            phase="scheduler",
            event_type="tick.completed",
            caused_by=tuple(event.event_id for event in committed),
            payload={
                "tick": tick,
                "actors": list(actors),
                "modules": [module.name for module in self.modules.modules],
                "accepted_intents": sum(1 for result in intent_results if result.accepted),
                "rejected_intents": sum(1 for result in intent_results if not result.accepted),
                "event_count_before_completion": len(committed),
            },
        )
        self._append(cache, timeline_id, [completion], committed, phase_counts)
        return TickResult(
            timeline_id=timeline_id,
            tick=tick,
            actors=actors,
            intent_results=tuple(intent_results),
            committed_events=tuple(committed),
            phase_counts=phase_counts,
        )

    def invalidate_cache(self, timeline_id: str | None = None) -> None:
        """Invalidate cached projections after out-of-band writes."""
        if timeline_id is None:
            self._projection_caches.clear()
        else:
            self._projection_caches.pop(timeline_id, None)

    def _cache(self, timeline_id: str) -> _ProjectionCache:
        cached = self._projection_caches.get(timeline_id)
        if cached is not None:
            return cached
        events = self.store.read(timeline_id)
        cached = _ProjectionCache(
            history=list(events),
            world=replay_world(events),
            planning=replay_planning(events),
            memory=replay_memory(events),
            knowledge=replay_knowledge(events),
        )
        self._projection_caches[timeline_id] = cached
        return cached

    def _append(
        self,
        cache: _ProjectionCache,
        timeline_id: str,
        candidates: list[NewEvent],
        committed: list[Event],
        phase_counts: dict[str, int],
    ) -> None:
        if not candidates:
            return
        appended = self.store.append_batch(
            timeline_id,
            candidates,
            expected_sequence=len(cache.history),
        )
        self._apply_committed(cache, appended, committed, phase_counts)

    def _apply_committed(
        self,
        cache: _ProjectionCache,
        appended: list[Event],
        committed: list[Event],
        phase_counts: dict[str, int],
    ) -> None:
        for event in appended:
            cache.history.append(event)
            apply_world_in_place(cache.world, event)
            apply_planning_in_place(cache.planning, event)
            apply_memory_in_place(cache.memory, event, self.memory.policy)
            apply_knowledge_in_place(cache.knowledge, event)
            committed.append(event)
            phase_counts[event.phase] = phase_counts.get(event.phase, 0) + 1

    @staticmethod
    def _knowledge_for_tick(
        knowledge: KnowledgeProjection, tick: int
    ) -> KnowledgeProjection:
        filtered = KnowledgeProjection()
        for observer_id, beliefs in knowledge.beliefs_by_observer.items():
            selected = {
                belief_id: belief
                for belief_id, belief in beliefs.items()
                if belief.updated_tick == tick
            }
            if selected:
                filtered.beliefs_by_observer[observer_id] = selected
        return filtered
