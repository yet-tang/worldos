# Phase I — Causal Runtime Hardening

Phase H established strict same-physical / different-memory causal experiments. Phase I hardens the runtime semantics exposed by final E2E acceptance.

## Goals

1. **Reachable idempotent replay for experimental writes**
   - `apply_physical_checkpoint` and `apply_memory_intervention` must return the original completed response when the exact same logical command is retried.
   - Replay must be decided before volatile current-hash checks or event reconstruction can change the request fingerprint.
   - Same key + different logical command must remain a conflict.

2. **Anchored causal eligibility**
   - Pre-treatment equivalence is evaluated once at the declared checkpoint and represented as an auditable deterministic attestation.
   - Post-outcome causal reports consume that attestation rather than re-evaluating physical equality after treatment has intentionally caused divergence.
   - Invalid/forged/stale attestations fail closed.

3. **Immediate intervention observability**
   - `retain`, `suppress`, `reinforce`, and `replace` must be observable through an effective-memory read view immediately after the intervention event, without requiring an extra world tick.
   - Historical raw memory events remain immutable.

4. **Deterministic identity audit**
   - Reproduce cross-world same-config/same-seed runs using truly identical `WorldConfig` values.
   - Runtime canonical hashes must not depend on catalog storage identity.
   - If remaining divergence is caused by intentionally different config fields such as `name`, report that explicitly rather than treating it as runtime nondeterminism.

## Safety invariants

- no direct SQLite mutation;
- all production writes remain event sourced;
- optimistic concurrency remains enforced on first execution;
- persistent command-ledger idempotency remains authoritative;
- no secret material in source, issues, or reports;
- existing production worlds remain untouched by acceptance.

## Acceptance target

Phase I is complete when final E2E demonstrates:

- exact retry of an experimental write returns `idempotency_replayed=true`;
- same key with a changed logical request returns conflict;
- a pre-treatment attestation created under equivalent state remains valid for a post-outcome causal report;
- negative-control/non-equivalent attestation cannot become eligible;
- memory interventions are visible immediately in effective-memory inspection;
- truly identical cross-world protocols reproduce event counts, evidence, and canonical hashes.
