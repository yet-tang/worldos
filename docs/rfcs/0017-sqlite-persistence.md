# RFC 0017: SQLite Persistence, Snapshots and Recovery

Status: Proposed

## Goal

WorldOS v1.1 requires a durable reference Event Store that preserves the v1 event, replay and branching semantics across process restarts without introducing an external service.

## Decisions

1. `SQLiteEventStore` implements the same public timeline, append and read operations as `InMemoryEventStore`.
2. SQLite uses WAL journaling, foreign keys and `synchronous=FULL`.
3. Every event batch is written inside one `BEGIN IMMEDIATE` transaction. A crash exposes the entire batch or none of it.
4. Optimistic concurrency compares `expected_sequence` with the visible history length, including inherited branch history.
5. Branches store only local events. Their inherited prefix remains defined by `parent_timeline_id` and `parent_through_sequence`.
6. Event IDs remain deterministic and use the same canonical input as the in-memory implementation.
7. Schema changes are recorded in `schema_migrations`. A database newer than the running kernel is rejected.
8. Snapshots are optional projection caches. They are keyed by timeline, sequence and projection name and include a canonical SHA-256 hash.
9. Snapshots never replace events as the source of truth. A snapshot beyond visible history is invalid.
10. Opening a store performs migrations; closing checkpoints the WAL. SQLite transaction recovery is the crash-recovery mechanism.

## Schema v1

- `schema_migrations(version)`
- `timelines(timeline_id, parent_timeline_id, parent_through_sequence)`
- `events(timeline_id, sequence, event_id, document)`
- `snapshots(timeline_id, sequence, projection, state_json, state_hash)`

## Compatibility

No external dependency is added: Python's standard-library `sqlite3` module is used. Existing code may continue using `InMemoryEventStore`; durable runners should use `SQLiteEventStore`.

## Verification

Acceptance tests must prove:

- reopen and replay preserve events and deterministic IDs;
- timelines and branch cutoffs survive restart;
- optimistic conflicts do not partially append;
- snapshots persist and respect history bounds;
- an interrupted uncommitted SQLite transaction is absent after reopening;
- SQLite integrity checks succeed.
