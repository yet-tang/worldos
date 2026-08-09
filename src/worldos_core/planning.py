from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any, Literal

from pydantic import BaseModel, Field

from .events import Event, NewEvent
from .intents import Intent
from .memory import MemoryProjection
from .world import WorldProjection

GoalStatus = Literal["active", "completed", "failed", "suspended"]
StepStatus = Literal["pending", "selected", "completed", "failed"]


class Goal(BaseModel):
    goal_id: str
    owner_id: str
    goal_type: str
    priority: int = 0
    status: GoalStatus = "active"
    parent_goal_id: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    created_tick: int = 0


class PlanStep(BaseModel):
    step_id: str
    goal_id: str
    action_type: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    status: StepStatus = "pending"
    ordinal: int = 0


class PlannerProjection(BaseModel):
    goals_by_owner: dict[str, dict[str, Goal]] = Field(default_factory=dict)
    steps_by_goal: dict[str, dict[str, PlanStep]] = Field(default_factory=dict)
    applied_event_ids: list[str] = Field(default_factory=list)

    def active_goals(self, owner_id: str) -> list[Goal]:
        goals = self.goals_by_owner.get(owner_id, {}).values()
        return sorted(
            [goal for goal in goals if goal.status == "active"],
            key=lambda goal: (-goal.priority, goal.created_tick, goal.goal_id),
        )

    def pending_steps(self, goal_id: str) -> list[PlanStep]:
        steps = self.steps_by_goal.get(goal_id, {}).values()
        return sorted(
            [step for step in steps if step.status == "pending"],
            key=lambda step: (step.ordinal, step.step_id),
        )


class PlanningContext(BaseModel):
    owner_id: str
    tick: int
    world: WorldProjection
    memory: MemoryProjection


class GoalPlanner:
    """Deterministic reference planner that converts explicit goals into intents."""

    def choose_goal(self, projection: PlannerProjection, owner_id: str) -> Goal | None:
        goals = projection.active_goals(owner_id)
        return goals[0] if goals else None

    def plan(self, goal: Goal, context: PlanningContext) -> list[NewEvent]:
        steps = self._steps_for(goal, context)
        return [
            NewEvent(
                tick=context.tick,
                phase="planning",
                event_type="plan.step_created",
                actor_id=goal.owner_id,
                subject_ids=(goal.owner_id,),
                correlation_id=goal.goal_id,
                payload=step.model_dump(mode="json"),
            )
            for step in steps
        ]

    def next_intent(self, projection: PlannerProjection, context: PlanningContext) -> Intent | None:
        goal = self.choose_goal(projection, context.owner_id)
        if goal is None:
            return None
        pending = projection.pending_steps(goal.goal_id)
        if not pending:
            return None
        step = pending[0]
        parameters = deepcopy(step.arguments)
        target_id = parameters.pop("target_id", None)
        return Intent(
            tick=context.tick,
            intent_type=step.action_type,
            actor_id=context.owner_id,
            target_id=target_id,
            parameters=parameters,
            correlation_id=goal.goal_id,
            metadata={"goal_id": goal.goal_id, "step_id": step.step_id},
        )

    def _steps_for(self, goal: Goal, context: PlanningContext) -> list[PlanStep]:
        if goal.goal_type in {"reach_location", "explore_location"}:
            destination = goal.parameters["location_id"]
            return [self._step(goal, 0, "move", {"to_location_id": destination})]
        if goal.goal_type == "defeat_entity":
            target_id = goal.parameters["target_id"]
            return [self._step(goal, 0, "attack", {"target_id": target_id})]
        if goal.goal_type == "eat":
            return [
                self._step(
                    goal,
                    0,
                    "eat",
                    {
                        "resource": goal.parameters.get("resource", "food"),
                        "quantity": goal.parameters.get("quantity", 1),
                        "relief": goal.parameters.get("relief", 45),
                    },
                )
            ]
        if goal.goal_type == "rest":
            return [self._step(goal, 0, "rest", {"relief": goal.parameters.get("relief", 40)})]
        if goal.goal_type == "request_resource":
            return self._targeted_steps(
                goal,
                context,
                "request_resource",
                {
                    "resource": goal.parameters.get("resource", "food"),
                    "quantity": goal.parameters.get("quantity", 1),
                },
            )
        if goal.goal_type == "help_resident":
            return self._targeted_steps(
                goal,
                context,
                "help_resident",
                {
                    "resource": goal.parameters.get("resource", "food"),
                    "quantity": goal.parameters.get("quantity", 1),
                },
            )
        if goal.goal_type == "repay_obligation":
            return self._targeted_steps(
                goal,
                context,
                "repay_obligation",
                {
                    "obligation_id": goal.parameters["obligation_id"],
                    "resource": goal.parameters.get("resource", "food"),
                    "quantity": goal.parameters.get("quantity", 1),
                },
            )
        if goal.goal_type == "strengthen_relationship":
            return self._targeted_steps(goal, context, "socialize", {})
        if goal.goal_type == "confront_rival":
            return self._targeted_steps(goal, context, "confront", {})
        if goal.goal_type == "survive":
            owner = context.world.entities.get(goal.owner_id)
            health = owner.components.get("health", {}) if owner else {}
            current = int(health.get("current", 100))
            maximum = max(1, int(health.get("maximum", 100)))
            if current * 2 < maximum and "safe_location_id" in goal.parameters:
                return [self._step(goal, 0, "move", {"to_location_id": goal.parameters["safe_location_id"]})]
            return []
        return []

    def _targeted_steps(
        self,
        goal: Goal,
        context: PlanningContext,
        action_type: str,
        arguments: dict[str, Any],
    ) -> list[PlanStep]:
        target_id = str(goal.parameters.get("target_id", ""))
        owner = context.world.entities.get(goal.owner_id)
        target = context.world.entities.get(target_id)
        if not target_id or owner is None or target is None or not target.active:
            return []
        steps: list[PlanStep] = []
        owner_location = owner.components.get("position", {}).get("location_id")
        target_location = target.components.get("position", {}).get("location_id")
        if target_location and owner_location != target_location:
            steps.append(self._step(goal, len(steps), "move", {"to_location_id": target_location}))
        action_arguments = {"target_id": target_id, **arguments}
        steps.append(self._step(goal, len(steps), action_type, action_arguments))
        return steps

    @staticmethod
    def _step(goal: Goal, ordinal: int, action_type: str, arguments: dict[str, Any]) -> PlanStep:
        canonical = json.dumps(
            {"goal_id": goal.goal_id, "ordinal": ordinal, "action_type": action_type, "arguments": arguments},
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(canonical.encode()).hexdigest()[:20]
        return PlanStep(
            step_id=f"step_{digest}",
            goal_id=goal.goal_id,
            action_type=action_type,
            arguments=deepcopy(arguments),
            ordinal=ordinal,
        )


_PLANNING_EVENTS = {
    "goal.created",
    "goal.status_changed",
    "plan.step_created",
    "plan.step_status_changed",
}


def reduce_planning(state: PlannerProjection, event: Event) -> PlannerProjection:
    if event.event_type not in _PLANNING_EVENTS:
        return state

    applied = [*state.applied_event_ids, event.event_id]

    if event.event_type == "goal.created":
        goal = Goal(**event.payload)
        owner_goals = dict(state.goals_by_owner.get(goal.owner_id, {}))
        owner_goals[goal.goal_id] = goal
        goals_by_owner = dict(state.goals_by_owner)
        goals_by_owner[goal.owner_id] = owner_goals
        return state.model_copy(update={"goals_by_owner": goals_by_owner, "applied_event_ids": applied})

    if event.event_type == "goal.status_changed":
        owner_id = event.payload["owner_id"]
        goal_id = event.payload["goal_id"]
        current = state.goals_by_owner[owner_id][goal_id]
        owner_goals = dict(state.goals_by_owner[owner_id])
        owner_goals[goal_id] = current.model_copy(update={"status": event.payload["status"]})
        goals_by_owner = dict(state.goals_by_owner)
        goals_by_owner[owner_id] = owner_goals
        return state.model_copy(update={"goals_by_owner": goals_by_owner, "applied_event_ids": applied})

    if event.event_type == "plan.step_created":
        step = PlanStep(**event.payload)
        goal_steps = dict(state.steps_by_goal.get(step.goal_id, {}))
        goal_steps[step.step_id] = step
        steps_by_goal = dict(state.steps_by_goal)
        steps_by_goal[step.goal_id] = goal_steps
        return state.model_copy(update={"steps_by_goal": steps_by_goal, "applied_event_ids": applied})

    goal_id = event.payload["goal_id"]
    step_id = event.payload["step_id"]
    current = state.steps_by_goal[goal_id][step_id]
    goal_steps = dict(state.steps_by_goal[goal_id])
    goal_steps[step_id] = current.model_copy(update={"status": event.payload["status"]})
    steps_by_goal = dict(state.steps_by_goal)
    steps_by_goal[goal_id] = goal_steps
    return state.model_copy(update={"steps_by_goal": steps_by_goal, "applied_event_ids": applied})


def replay_planning(events: list[Event], initial: PlannerProjection | None = None) -> PlannerProjection:
    state = initial.model_copy(deep=True) if initial else PlannerProjection()
    for event in events:
        state = reduce_planning(state, event)
    return state
