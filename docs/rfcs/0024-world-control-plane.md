# RFC 0024 — World Control Plane v0.1

## Status

Development-stage implementation.

## Problem

World Creator can create independent worlds and Inspector can observe them, but users cannot advance a selected world from the web UI. Putting write actions directly into Inspector would blur the read-only observation boundary.

The Chinese UI also exposed internal English identifiers such as `agrarian_town`, `agrarian`, `Tick`, and development implementation labels. Internal identifiers should remain stable for code and persistence, while the user-facing Chinese surface should render localized labels.

## Decision

WorldOS introduces a minimal Control Plane beside the read-only Inspector.

```text
World Creator
    ↓
World database
    ↓
Control Plane ── run 1 / 10 / 100 turns ──> WorldRunner
    ↓                                      ↓
Inspector <──────── read projections ───── Event Store
```

### Boundaries

- Inspector remains read-only.
- Control Plane is the explicit write boundary for web-triggered world execution.
- Control Plane does not write projection state or SQLite rows directly.
- All execution goes through `WorldRunner`, which in turn uses the normal tick engine and event store.
- One in-process writer lock is maintained per world database so two web run commands cannot execute concurrently in the same console process.
- SQLite/Event Store conflict checks remain the final protection against out-of-process concurrent writers.

### v0.1 controls

The first UI exposes only deterministic bounded operations:

- run 1 turn
- run 10 turns
- run 100 turns

Pause/resume, background continuous execution, snapshots, branch creation, and deletion are intentionally deferred.

### Localization

Persistence and code keep stable identifiers such as `agrarian_town` and `future`. The Chinese UI maps them to human-readable labels and no longer exposes raw enum values as primary presentation.

Known development terminology in the default Chinese view is localized:

- Tick → 回合
- Narrator → 叙事器
- Inspector → 世界观察台
- World Seed → 世界种子
- Living World → 持续演化世界

The product name `WorldOS` remains unchanged.

## Acceptance criteria

- A created world at turn 0 can be advanced from the web UI.
- Running 1 turn changes the selected world to turn 1 and increases its event count.
- Running 10 more turns advances the same world from turn 1 to turn 11.
- Control actions apply only to the world selected by the browser cookie.
- World execution uses `WorldRunner`; the Control Plane never mutates projections or database rows directly.
- The default Chinese creation page does not display the previous mixed English development labels.
- Existing Inspector read APIs remain unchanged.
