# RFC 0010: Layered Memory Architecture

## Status

Draft implementation baseline.

## Decision

WorldOS memory is an event-sourced projection derived from character knowledge. Memory is not hidden mutable state inside an agent and is not equivalent to world truth.

The runtime defines four memory classes:

- **Working memory**: bounded, immediately available context. Oldest records are deactivated when capacity is exceeded.
- **Episodic memory**: durable records of perceived events.
- **Semantic memory**: consolidated beliefs about entities and the world.
- **Identity memory**: beliefs that contribute to an agent's self-model, role, and affiliations.

## Pipeline

```text
World Event
→ Observation
→ Belief
→ Memory Derivation
→ memory.recorded
→ Memory Projection
```

Every memory record retains its owner, source belief identifiers, confidence, salience, tick, and content. Replay uses committed memory events and never reruns an LLM.

## Determinism

Memory identifiers are derived from belief identifiers and semantic keys. Iteration order is sorted. Capacity eviction is deterministic and deactivates the oldest working-memory record.

## Forgetting

Forgetting is explicit through `memory.forgotten`. Historical events are retained; only the active projection changes.

## Invariants

1. Characters cannot remember facts they did not know.
2. Memory writes occur only through events.
3. Working-memory capacity is bounded by policy.
4. Replay produces the same active and inactive memory records.
5. Memory events do not mutate the physical world projection.
