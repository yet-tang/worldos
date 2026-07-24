# RFC-0015: Narrator Read API

## Status

Draft

## Summary

WorldOS exposes a deterministic read-only API that prepares narrative context from `WorldInspector`. The narrator consumes committed history and projections but has no Event Store reference and no mutation capability.

## Goals

- provide omniscient narrative material for world-level narration
- provide actor-scoped narrative material without leaking unobserved world truth
- support historical sequence cutoffs and incremental sequence windows
- preserve authoritative event order
- expose structured context instead of coupling the runtime to a text-generation model
- keep narration outside world state transitions

## API

`NarratorReadAPI` is constructed with a `WorldInspector` and exposes:

- `context(...)`

The method returns a `NarrativeContext` containing timeline identity, visible sequence, perspective mode, and structured narrative inputs.

Omniscient mode includes visible committed events and the canonical world hash.

Actor mode includes only source events explicitly referenced by that actor's observations, together with the actor's observations, beliefs, memories, goals, and plan steps. It intentionally omits the canonical world hash because that hash commits to world facts outside the actor's knowledge.

`NarrativeEvent` is a stable, serialization-friendly event view. It omits store and timeline mutation capabilities.

## Invariants

1. The narrator receives a `WorldInspector`, never an Event Store.
2. Calling the API performs no writes.
3. Omniscient events preserve committed sequence order.
4. Actor-scoped events are limited to explicitly observed source events.
5. Unobserved entities, locations, and state are not exposed through actor-scoped event material.
6. Historical contexts use the same inclusive sequence cutoff as the inspector.
7. `from_sequence` only narrows narrative material; it never changes replay state.
8. Text generation is downstream of this API and cannot feed events back into the world.

## Non-Goals

- prose generation
- dialogue generation
- event mutation
- inferred omniscience for actor perspectives
- persistence of generated narration

## Future Work

A renderer may transform `NarrativeContext` into prose, dialogue, summaries, or scene descriptions. Renderers must remain pure consumers. If generated text is persisted, it must live in a separate derived-content store rather than the authoritative world event stream.
