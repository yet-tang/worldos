# RFC 0033 — Projection-neutral extension events

Status: Accepted

## Problem

WorldOS stores events for several projections in one timeline. The world projection historically raised when it encountered an event type it did not own. That made an otherwise durable timeline unreplayable when a remote-control stimulus or future module event was appended before a world reducer existed for it.

The failure was observed during Remote Control API acceptance: `world.external_stimulus` was durably appended, then the post-write projection replay failed. The HTTP command failed before its Command Ledger entry completed, while the event itself remained committed.

## Decision

A projection MUST ignore event types it does not own. Unknown/extension events are projection-neutral for that projection.

For `WorldProjection` this means:

- registered world mutation events continue to use strict reducers;
- known non-world events remain projection-neutral;
- unknown extension/stimulus events are also projection-neutral;
- a future-tick extension event may advance the projection's tick, but MUST NOT mutate entities, flags, or canonical state;
- the event remains present in the Event Store and remains visible to inspectors, narrators, debugging tools, and future projections that choose to understand it.

This matches the existing behavior of knowledge, memory, planning, and social projections, which ignore unrelated events.

## Consequences

Adding a new event family no longer requires every existing projection to be upgraded atomically. Historical worlds containing extension events remain replayable after restart.

A projection that claims an event type remains responsible for validating that event's payload. Unknown events are not silently converted into world mutations.

## Recovery

A world made unreadable solely by the former unknown-event behavior recovers automatically after upgrading: replay treats the extension event as neutral, so the normal hash-protected delete/advance/debug paths work again. No direct SQLite surgery or unsafe force-delete endpoint is required for this incident class.

## Tests

Regression coverage MUST prove that:

1. `world.external_stimulus` can exist in history without changing canonical world state;
2. replay remains deterministic;
3. future extension events do not mutate entities or flags;
4. existing registered reducers remain strict.
