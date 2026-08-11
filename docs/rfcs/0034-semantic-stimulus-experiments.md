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

Each is serialized as `world.stimulus.<kind>` with `semantic_stimulus=true` metadata. These events are extension events: durable and queryable, while projections that do not own their semantics remain replay-safe.

This phase intentionally does **not** pretend that a semantic stimulus already changes survival/economy mechanics. The event records the intervention. Domain modules may consume specific stimulus families in later phases. This separation prevents transport/tool schemas from silently inventing simulation behavior.

## Agent workflow

1. Probe the explicit world/timeline and retain its canonical hash.
2. Create an experiment branch from a known history point.
3. Apply a typed semantic stimulus to the experiment branch with an idempotency key.
4. Advance control and experiment timelines as required.
5. Compare both probes using `compare_timelines`.
6. Inspect changed actors/events/social state and narrator context before drawing a conclusion.

## Safety

All semantic writes reuse the existing Control API and Command Ledger. They require an explicit world ID, timeline, expected world hash, idempotency key and reason. Raw `inject_world_event` remains available for engineering/debugging but is no longer the preferred experiment interface.

## Comparison

`compare_timelines` is read-only and reports control/experiment ticks, event counts, hashes and actor-level probe differences. It deliberately reports observations rather than causal claims.

## Next step

Add domain consumers for semantic stimuli, starting with resource shocks in the survival/economy module, then expose richer aggregate outcome metrics (hunger, health, wealth, trade, trust, conflict, rumor spread) for experiments.
