# RFC 0018: Needs and Deterministic Decision Loop

## Status

Accepted for WorldOS v1.1.

## Context

WorldOS v1 could execute explicit goals, but characters could not create goals from their own state. A living world requires a deterministic bridge from physical state to motivation while preserving replayability and keeping language models outside the authoritative runtime.

## Decision

Character entities may expose two components:

- `needs`: a mapping from need name to severity in the inclusive range 0–100.
- `need_policies`: deterministic threshold and goal templates for each need.

At the beginning of each tick, after `before_actions` world modules and before planning, the `NeedEngine`:

1. scans active character entities in stable entity-id order;
2. emits `need.assessed` for every configured need;
3. compares severity with the configured threshold;
4. creates at most one active goal per owner and need type;
5. records `source_need` in goal parameters;
6. lets the existing planner convert the selected goal into an intent.

Stable identifiers are derived from canonical owner, need, tick, goal type and parameters. The engine performs no random sampling and makes no external calls.

## Event model

`need.assessed` is a cognitive audit event and does not mutate the physical world projection. Its payload contains:

- `need_id`
- `owner_id`
- `need_type`
- `severity`
- `threshold`
- `tick`
- `goal_type`
- `goal_parameters`

Goals remain represented by the existing `goal.created` event and therefore replay through the existing planning projection.

## Tick order

```text
world modules: before_actions
→ need assessment
→ need-derived goal creation
→ goal selection
→ plan materialization
→ intent validation and resolution
→ world effects
→ perception, belief and memory
```

## Safety and determinism

- Need values and thresholds are clamped to 0–100.
- Inactive and non-character entities are ignored.
- Existing active goals carrying the same `source_need` suppress duplicate goal creation.
- Need events are audit-only and cannot change the canonical physical-world hash.
- Identical history and tick produce identical assessments, goals, intents and effects.

## Consequences

This establishes the first autonomous decision loop:

```text
World State → Need → Goal → Plan → Intent → Effect
```

Future survival and economy modules may update need component values, while richer policy systems may resolve competing goals. Those modules must preserve this event-sourced boundary.
