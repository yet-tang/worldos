# RFC 0023 — World Creation and World Catalog

## Status

Proposed for the development-stage World Creator implementation.

## Problem

`First Living World` is a useful acceptance scenario, but its locations, residents and initial conditions are hard-coded. The runtime therefore proves that a world can execute without yet providing a product-level way to create different worlds.

World creation must not bypass the event-sourced constitution. A form submission or configuration file is an input to creation, not world state itself.

## Decision

World creation uses four layers:

```text
World Template
      ↓
WorldConfig
      ↓
Bootstrap Compiler
      ↓
Canonical NewEvent batch
      ↓
SQLite Event Store / main timeline
      ↓
WorldOS Runtime
```

### WorldConfig

The first contract exposes:

- name
- world type
- civilization era
- population
- location count
- resource abundance
- social stability
- selected initial conflicts
- deterministic world seed

The public contract is validated before any database is created.

### Bootstrap Compiler

The compiler is deterministic. The same validated `WorldConfig` and seed produce the same ordered bootstrap event content.

The compiler emits standard events only, currently:

- `world.created`
- `entity.created` for locations
- `entity.created` for characters

Initial jobs, inventories, needs, health, relationships, rumors, conflicts and trade offers are entity components in the bootstrap event payload. Subsequent runtime changes remain normal events produced by modules and the tick engine.

### Independent world databases

Independent created worlds are not timelines of one another. Each world receives a separate SQLite database under:

```text
<data-dir>/worlds/<world-id>.db
```

Timelines remain reserved for alternate histories *inside* one world.

This distinction is intentional:

```text
World A.db
  main
  branch-1
  branch-2

World B.db
  main
  branch-1
```

### World Catalog

A development-stage catalog records created worlds in:

```text
<data-dir>/worlds/catalog.json
```

The legacy `<data-dir>/world.db` remains visible as `first-living-world` when present, so existing development data is not migrated or overwritten.

Catalog metadata is not authoritative world state. The SQLite event log remains authoritative.

## Web flow

The Inspector HTTP process becomes a small WorldOS console:

```text
/
  My Worlds + Create World

/world/<world-id>
  Inspector 2.0 for selected world

POST /api/worlds
  Validate config → compile → create independent DB
```

A browser cookie selects which world database the existing read-only Inspector APIs query. Inspector projections remain read-only. Creation is the only write operation in this console phase and only writes the initial event batch to a new database.

## Determinism

The compiler derives a stable integer random seed from SHA-256 of the user seed rather than relying on process entropy.

Creation timestamps exist only in catalog metadata and are not emitted into bootstrap events, so they do not affect canonical world hashes.

## Constraints

This RFC does not introduce the World Control Plane. The creator does not run, pause, resume, mutate or delete an existing world.

Running a created world continues to use `WorldRunner` / `worldos-living run` against that world's database until a later control-plane RFC adds authenticated runtime controls.

## Acceptance criteria

- Same config + seed compiles to identical bootstrap event content.
- Different worlds have independent database paths.
- A created world replays through the existing world projection.
- A created world can execute at least one normal runtime tick through `WorldRunner`.
- Existing `First Living World` remains visible when its legacy database exists.
- The web creator can create a world and immediately open it in Inspector 2.0.
- Inspector reads do not mutate the selected world.
