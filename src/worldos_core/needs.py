from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel, Field

from .events import Event, NewEvent
from .planning import Goal, PlannerProjection
from .world import WorldProjection


DEFAULT_NEED_POLICIES: dict[str, dict[str, Any]] = {
    "hunger": {
        "threshold": 70,
        "goal_type": "eat",
        "parameters": {"resource": "food", "quantity": 1, "relief": 45},
    },
    "fatigue": {
        "threshold": 75,
        "goal_type": "rest",
        "parameters": {"relief": 40},
    },
}


class NeedAssessment(BaseModel):
    need_id: str
    owner_id: str
    need_type: str
    severity: int
    threshold: int
    tick: int
    goal_type: str
    goal_parameters: dict[str, Any] = Field(default_factory=dict)


class NeedsProjection(BaseModel):
    latest_by_owner: dict[str, dict[str, NeedAssessment]] = Field(default_factory=dict)
    applied_event_ids: list[str] = Field(default_factory=list)

    def assessments(self, owner_id: str) -> list[NeedAssessment]:
        return sorted(
            self.latest_by_owner.get(owner_id, {}).values(),
            key=lambda item: (-item.severity, item.need_type, item.need_id),
        )


class NeedEngine:
    """Derives deterministic goals from character state without consulting an LLM."""

    def derive(
        self,
        world: WorldProjection,
        planning: PlannerProjection,
        *,
        tick: int,
    ) -> list[NewEvent]:
        events: list[NewEvent] = []
        for owner_id, entity in sorted(world.entities.items()):
            if not entity.active or entity.kind != "character":
                continue
            for assessment in self._assess(owner_id, entity.components, tick):
                events.append(
                    NewEvent(
                        tick=tick,
                        phase="cognition",
                        event_type="need.assessed",
                        actor_id=owner_id,
                        subject_ids=(owner_id,),
                        correlation_id=assessment.need_id,
                        payload=assessment.model_dump(mode="json"),
                    )
                )

                active_need_goals = self._active_goals_for_need(
                    planning, owner_id, assessment.need_type
                )
                compatible = [
                    goal
                    for goal in active_need_goals
                    if goal.goal_type == assessment.goal_type
                ]

                if assessment.severity < assessment.threshold:
                    for goal in active_need_goals:
                        events.append(self._status_event(goal, tick, "suspended"))
                    continue

                if compatible:
                    continue

                # Older worlds created before explicit self-care policies may still
                # carry active `survive` goals for hunger/fatigue. Retire those stale
                # goals instead of letting them block the new eat/rest behavior.
                for goal in active_need_goals:
                    events.append(self._status_event(goal, tick, "suspended"))

                goal = self._goal_for(assessment)
                events.append(
                    NewEvent(
                        tick=tick,
                        phase="cognition",
                        event_type="goal.created",
                        actor_id=owner_id,
                        subject_ids=(owner_id,),
                        correlation_id=goal.goal_id,
                        payload=goal.model_dump(mode="json"),
                    )
                )
        return events

    def _assess(self, owner_id: str, components: dict[str, Any], tick: int) -> list[NeedAssessment]:
        configured = components.get("needs", {})
        policies = components.get("need_policies", {})
        result: list[NeedAssessment] = []
        for need_type, raw_value in sorted(configured.items()):
            policy = dict(DEFAULT_NEED_POLICIES.get(need_type, {}))
            configured_policy = policies.get(need_type, {}) if isinstance(policies, dict) else {}
            if isinstance(configured_policy, dict):
                policy.update(configured_policy)
            severity = max(0, min(100, int(raw_value)))
            threshold = max(0, min(100, int(policy.get("threshold", 60))))
            goal_type = str(policy.get("goal_type", "survive"))
            parameters = dict(policy.get("parameters", {}))
            need_id = self._stable_id(owner_id, need_type, tick)
            result.append(
                NeedAssessment(
                    need_id=need_id,
                    owner_id=owner_id,
                    need_type=need_type,
                    severity=severity,
                    threshold=threshold,
                    tick=tick,
                    goal_type=goal_type,
                    goal_parameters=parameters,
                )
            )
        return result

    @staticmethod
    def _active_goals_for_need(
        planning: PlannerProjection, owner_id: str, need_type: str
    ) -> list[Goal]:
        return [
            goal
            for goal in planning.active_goals(owner_id)
            if goal.parameters.get("source_need") == need_type
        ]

    @staticmethod
    def _status_event(goal: Goal, tick: int, status: str) -> NewEvent:
        return NewEvent(
            tick=tick,
            phase="cognition",
            event_type="goal.status_changed",
            actor_id=goal.owner_id,
            subject_ids=(goal.owner_id,),
            correlation_id=goal.goal_id,
            payload={
                "owner_id": goal.owner_id,
                "goal_id": goal.goal_id,
                "status": status,
            },
        )

    @staticmethod
    def _goal_for(assessment: NeedAssessment) -> Goal:
        parameters = dict(assessment.goal_parameters)
        parameters["source_need"] = assessment.need_type
        canonical = json.dumps(
            {
                "owner_id": assessment.owner_id,
                "need_type": assessment.need_type,
                "tick": assessment.tick,
                "goal_type": assessment.goal_type,
                "parameters": parameters,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(canonical.encode()).hexdigest()[:20]
        return Goal(
            goal_id=f"goal_need_{digest}",
            owner_id=assessment.owner_id,
            goal_type=assessment.goal_type,
            priority=assessment.severity,
            parameters=parameters,
            created_tick=assessment.tick,
        )

    @staticmethod
    def _stable_id(owner_id: str, need_type: str, tick: int) -> str:
        canonical = f"{owner_id}:{need_type}:{tick}"
        return f"need_{hashlib.sha256(canonical.encode()).hexdigest()[:20]}"


def reduce_needs(state: NeedsProjection, event: Event) -> NeedsProjection:
    next_state = state.model_copy(deep=True)
    if event.event_type != "need.assessed":
        return next_state
    assessment = NeedAssessment(**event.payload)
    next_state.latest_by_owner.setdefault(assessment.owner_id, {})[
        assessment.need_type
    ] = assessment
    next_state.applied_event_ids.append(event.event_id)
    return next_state


def replay_needs(events: list[Event], initial: NeedsProjection | None = None) -> NeedsProjection:
    state = initial.model_copy(deep=True) if initial else NeedsProjection()
    for event in events:
        state = reduce_needs(state, event)
    return state
