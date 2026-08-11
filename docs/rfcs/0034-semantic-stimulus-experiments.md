# RFC 0034 — Semantic Stimulus and Timeline Experiments

## Status
Implemented in Phase D.

## Goal
Move WorldOS agents from raw event construction to explicit, typed experimental interventions and deterministic timeline comparison.

## Stimulus contract
WorldOS exposes five initial intervention families:

- `resource_shock`: resource + magnitude + duration
- `environment_event`: magnitude + duration + optional location
- `spread_information`: message + optional target actors/location
- `social_incident`: magnitude + optional actors/location
- `policy_change`: policy + magnitude + duration

Each is serialized as `world.stimulus.<kind>` with `semantic_stimulus=true` metadata. These events are durable, queryable extension events; projections that do not own their semantics remain replay-safe.

## Causal domain consumption

`resource_shock` is the first stimulus with authoritative simulation semantics. `SurvivalEconomyModule` reads active resource shocks from timeline history. A shock begins affecting production on the next authoritative tick and remains active for `duration_ticks`. Its `magnitude` is a relative production modifier clamped to -100%..+100%; overlapping shocks combine deterministically within the same clamp.

Example: food magnitude `-0.4` for 30 ticks lowers food job output by 40% during that interval. The underlying job rate is not mutated, so production returns to baseline when the shock expires. Audit `resource.produced` events record `base_quantity`, actual `quantity`, and `stimulus_modifier`.

The other four stimulus families are currently typed, durable interventions but do not yet claim domain-mechanical effects. Their consumers must be added explicitly rather than smuggling simulation rules into the transport layer.

## Agent workflow

1. Probe the explicit world/timeline and retain its canonical hash.
2. Create an experiment branch from a known history point.
3. Apply a typed semantic stimulus to the experiment branch with an idempotency key.
4. Advance control and experiment timelines as required.
5. Compare both probes using `compare_timelines`.
6. Inspect aggregate outcome metrics, changed actors/events/social state, and narrator context before drawing a conclusion.

## Safety

All semantic writes reuse the existing Control API and Command Ledger. They require an explicit world ID, timeline, expected world hash, idempotency key and reason. Raw `inject_world_event` remains available for engineering/debugging but is no longer the preferred experiment interface.

## Comparison

`compare_timelines` is read-only. It reports control/experiment ticks, event counts, hashes, actor-level probe differences, and aggregate outcome metrics including average hunger/fatigue/health, total wealth, inventory totals, and recent production/trade/conflict/rumor activity. It reports observations and deltas, not causal certainty.

## Next step

Use a real branched world to validate that a resource shock produces measurable divergence. Then add explicit domain consumers for information, environmental, social and policy stimuli only where the world model has clear causal semantics.
