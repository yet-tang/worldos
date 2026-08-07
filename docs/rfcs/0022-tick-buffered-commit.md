# RFC 0022: Tick-buffered atomic commit

## Status

Proposed.

## Problem

A Living World tick emits hundreds of events. Committing every scheduler phase and actor action through an independent SQLite transaction causes repeated transaction setup, visible-count queries, JSON writes, and durable syncs. Projection caching removes replay amplification but does not remove this write amplification.

## Decision

The SQLite event store supports one active buffered batch per timeline and process.

- `begin_buffer(timeline_id)` captures the visible sequence.
- `append_batch(...)` validates optimistic concurrency against the buffered head and returns fully materialized deterministic `Event` objects without writing them yet.
- `commit_buffer(timeline_id)` inserts every buffered event in sequence order within one `BEGIN IMMEDIATE` transaction.
- `rollback_buffer(timeline_id)` discards the uncommitted events.
- The deterministic tick engine wraps a complete tick in this lifecycle when the store provides it.
- In-memory stores keep their existing immediate behavior.

The buffer is private to a single writer. Reads do not expose uncommitted events; the tick engine relies on its projection cache while the buffer is active.

## Guarantees

- A completed tick is committed atomically.
- A failed tick leaves no partial `tick.started`, intent, effect, observation, or memory events.
- Event sequence numbers and deterministic event IDs are unchanged from immediate append semantics.
- Optimistic concurrency is checked both when the buffer starts and when it commits.
- Timeline branching, replay, snapshots, and Inspector APIs continue to read only committed history.

## Validation

- equivalent event streams between in-memory immediate writes and SQLite buffered writes
- rollback after an injected mid-tick failure
- concurrency conflict if another writer advances the timeline before commit
- exactly one SQLite write transaction per completed tick
- Living World active-phase benchmarks at 1, 5, 10, 20, and 100 ticks
