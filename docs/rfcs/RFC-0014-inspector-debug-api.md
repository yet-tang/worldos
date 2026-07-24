# RFC-0014: Inspector and Debug API

## Status

Draft

## Summary

WorldOS exposes a read-only inspector that reconstructs runtime state from committed events. The inspector never mutates projections, appends events, or bypasses replay.

## Goals

- inspect a timeline at the latest sequence or a historical sequence
- filter committed events by type, actor, subject, tick, and correlation
- inspect one entity's physical state
- inspect one actor's observations, beliefs, memories, goals, and plan steps
- explain direct event causality through `caused_by`
- support inherited history on branched timelines

## API

`WorldInspector` is constructed with an `InMemoryEventStore` and exposes:

- `events(...)`
- `snapshot(...)`
- `entity(...)`
- `actor(...)`
- `explain_event(...)`

`TimelineSnapshot` contains timeline metadata, visible event count, replayed world state, and canonical world hash.

`ActorDebugView` joins independent replay projections for diagnostics only. It does not merge world truth with actor knowledge semantically.

## Invariants

1. All returned state is derived from committed events.
2. Historical inspection uses an inclusive visible sequence cutoff.
3. Inspection performs no writes.
4. Event filters preserve authoritative sequence order.
5. Actor knowledge and memory remain observer-scoped.
6. Branch inspection includes inherited parent history through the branch cutoff.
7. Causality explanation reports only explicit `caused_by` edges; it does not infer hidden causes.

## Projection Compatibility

Audit and cognitive events are explicit no-ops for the physical world reducer. This includes intent audit events, observations, beliefs, memories, goals, plan lifecycle events, and scheduler boundaries. Domain module events must still use registered physical event types when they intend to change world state.

## Future Work

A transport layer may later expose this facade through HTTP, GraphQL, a CLI, or a visual debugger. Those layers must preserve the read-only contract.
