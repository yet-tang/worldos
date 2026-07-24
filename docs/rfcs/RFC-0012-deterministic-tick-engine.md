# RFC-0012: Deterministic Tick Engine

## Status

Proposed

## Summary

WorldOS advances a timeline through an explicit deterministic tick scheduler. A tick coordinates existing projections and runtimes without granting any agent direct authority over world state.

## Canonical phase order

1. `tick.started`
2. actor discovery and stable ordering
3. goal selection and plan materialization
4. intent validation and deterministic resolution
5. plan-step status transition
6. observation and belief derivation
7. memory derivation
8. `tick.completed`

Actors are ordered lexicographically by entity identifier. Goals and steps retain their own deterministic ordering rules. All random-looking outcomes continue to use the world seed and deterministic intent identifiers.

## Invariants

- A completed tick cannot be executed twice on the same timeline.
- Every write uses optimistic sequence validation.
- Agents emit intents; only action rules emit authoritative world effects.
- Perception consumes committed action events, never speculative intents.
- Memory consumes beliefs updated in the current tick, avoiding repeated derivation from historical beliefs.
- `tick.completed` records actors, accepted and rejected intent counts, and the number of preceding events.
- Replaying identical history with the same world seed produces identical event envelopes and event identifiers.
- Timeline branches execute independently from their inherited cutoff.

## Failure model

A raised exception prevents `tick.completed` from being written. The presence of `tick.started` without `tick.completed` therefore represents an interrupted tick and remains visible for inspection. Recovery and resumable phase checkpoints are deferred to the persistent event-store milestone.

## Reference API

```python
engine = DeterministicTickEngine(store, world_seed="world-1")
result = engine.run_tick("main", tick=42)
```

`TickResult` exposes the participating actors, intent results, committed events, and per-phase counts.
