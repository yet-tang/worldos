# RFC 0011: Goal Tree and Planner Runtime

Status: Draft

## Purpose

Define replayable goals and deterministic planning without allowing cognition to mutate world state.

## Invariants

1. Goals are explicit event-sourced records owned by an entity.
2. Parent-child links form a goal tree; they do not imply automatic completion.
3. Goal selection is deterministic: priority descending, then creation tick, then goal id.
4. Plans are projections made of explicit `plan.step_created` events.
5. A planner reads world and memory projections but writes only planning events or Intents.
6. Intents preserve `goal_id` and `step_id` metadata for feedback and auditability.
7. Replay never reruns an LLM. It replays committed goal, plan, intent, and outcome events.

## Events

- `goal.created`
- `goal.status_changed`
- `plan.step_created`
- `plan.step_status_changed`

## Reference goal types

The v1 reference planner supports:

- `reach_location` -> `move`
- `defeat_entity` -> `attack`
- `survive` -> conditionally move to a configured safe location

World packages may register richer goal decomposers later, provided their outputs are deterministic or committed as events.

## Feedback loop

Action outcomes should eventually emit feedback events that update step and goal status. This RFC establishes the durable data model and the one-way planner-to-intent boundary; scheduler integration is specified by the scheduler RFC.
