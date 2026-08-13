# Phase H — Experimental State Control

Phase H turns strict causal experiments into a first-class WorldOS capability.

## Invariants

1. **Event sourced** — interventions append events; they never mutate SQLite projections directly.
2. **Hash guarded** — every write is protected by optimistic concurrency against the intended timeline state.
3. **Idempotent** — every public write participates in the persistent command ledger.
4. **Deterministic** — identical checkpoint, intervention, seed, stimulus, and ticks produce identical evidence and outcome.
5. **Auditable** — treatment, control, pre-treatment equivalence, intervention events, and outcomes remain queryable.
6. **Physical/experiential separation** — experiments distinguish physical actor state from memory/history state.

## Delivery slices

### H1 — Experimental checkpoint

Capture a timeline checkpoint with a canonical physical-state manifest for selected actors/components. The manifest records source timeline, sequence/hash, selected fields, and a deterministic digest.

### H2 — Physical-state override

Apply a checkpoint manifest to another experimental branch through normal component events. The operation must be hash guarded, idempotent, and reject unsupported/non-physical components.

Initial physical allowlist:

- inventory
- wallet
- health
- needs
- survival
- position
- food_security
- production_carry

Adaptive strategy and episodic memory are deliberately excluded from physical override.

### H3 — Memory intervention

Support explicit experimental treatment without rewriting historical events:

- `retain` — no treatment; historical memory remains effective
- `suppress` — selected memories remain auditable but are excluded from adaptive influence on this branch
- `reinforce` — selected memory classes receive an experimental reinforcement multiplier
- `replace` — suppress a selected class and introduce an explicit experimental memory treatment

Interventions must be represented by dedicated events and consumed by the adaptive-memory projection/runtime.

### H4 — Experiment protocol

First-class protocol:

`checkpoint -> branch treatment/control -> equalize physical state -> memory intervention -> verify equivalence -> stimulus -> symmetric advance -> compare`

Before treatment, the protocol reports:

- physical-state equality
- seed equality
- lineage/checkpoint identity
- intentional differing variables
- unexpected differences

### H5 — Causal report

A causal report must identify treatment rather than merely report event deltas.

Minimum shape:

```text
Treatment:
  memory.scarcity = retained
Control:
  memory.scarcity = suppressed

Pre-treatment equivalence:
  physical_state = identical
  seed = identical
  checkpoint = identical

Outcomes:
  hoarding_onset_delta
  conflict_propensity_delta
  preferred_partner_delta
  conflict_onset_delta

Attribution:
  declared memory intervention
```

## Acceptance target

Phase H is complete only when an E2E experiment demonstrates two branches with identical physical state and deterministic runtime inputs, but different declared memory treatment, followed by reproducible behavioral divergence attributable to that treatment. Existing production worlds must remain untouched during acceptance.
