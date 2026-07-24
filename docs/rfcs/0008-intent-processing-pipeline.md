# RFC 0008: Intent Processing Pipeline

Status: Draft

## Summary

World entities and AI agents may request actions only by submitting an `Intent`. An intent is not an event and cannot mutate projected state. The runtime converts it through a deterministic pipeline:

```text
Intent
  -> Validation
  -> Resolution
  -> Event Batch
  -> Atomic Append
  -> Projection
```

## Required invariants

1. Rules validate against a projection reconstructed from committed history.
2. Accepted intents resolve to one non-empty event batch.
3. Every event in a resolved batch uses the intent tick and one correlation identifier.
4. Random outcomes are derived from explicit seed material and written into resolution events.
5. Event batches append atomically under optimistic concurrency control.
6. Rejected and unsupported intents create an `intent.rejected` audit event but no world-state effect.
7. Reducers consume events only; they never inspect or execute intents.

## Initial reference rules

The first runtime includes `move` and `attack` rules. They establish the extension contract for future world packages without embedding LLM behavior in the deterministic kernel.

## Non-goals

This RFC does not define planning, memory retrieval, natural-language narration, asynchronous scheduling, or an external database Event Store.
