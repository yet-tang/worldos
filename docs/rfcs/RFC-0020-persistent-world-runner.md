# RFC 0020: Persistent World Runner

## Status

Accepted for WorldOS v1.1.

## Context

WorldOS can persist timelines and execute deterministic ticks, but it still needs an operational boundary that owns process lifecycle, pause/resume controls, autosave, recovery, branching, and runtime metrics.

The runner must not become a second source of world truth. World state remains event-sourced and deterministic; process timing and throughput are operational observations only.

## Decision

`WorldRunner` wraps `SQLiteEventStore` and `DeterministicTickEngine` and provides:

- `run(ticks)`: execute up to a bounded number of ticks and stop early when paused;
- `step(count)`: advance explicitly, including while paused;
- `pause()` / `resume()`: append replay-safe runner control events;
- `status()`: report timeline, completed tick, event count, world hash, snapshot position, recovery source, and current-process metrics;
- `branch()`: create a persistent timeline branch at an explicit sequence;
- periodic world projection snapshots;
- startup recovery for incomplete ticks.

The CLI exposes the same lifecycle through:

```text
worldos-core world-init --db world.db
worldos-core run --db world.db --ticks 100
worldos-core pause --db world.db
worldos-core step --db world.db --ticks 1
worldos-core resume --db world.db
worldos-core status --db world.db
worldos-core branch --db world.db experiment --through-sequence 250
```

## Recovery model

A tick currently commits multiple atomic event batches. A process failure can therefore leave `tick.started` without a matching `tick.completed`.

Recovery never mutates or deletes that history. Instead it:

1. finds the latest unmatched `tick.started`;
2. creates a recovery timeline branching immediately before that event;
3. appends `runner.recovered` on the new timeline;
4. continues execution from the last completed tick.

This preserves forensic history while restoring a deterministic continuation path.

## Determinism boundary

The following runner events are audit-only no-ops in the world projection:

- `runner.paused`
- `runner.resumed`
- `runner.recovered`

Wall-clock durations and throughput are not persisted into authoritative history. They are returned as session-local `RunnerMetrics`, preventing machine performance from changing replay hashes.

## Snapshots

At a configurable completed-tick interval, the runner stores the full world projection and canonical hash under the `world` projection name. Snapshots are accelerators and integrity aids; the event log remains authoritative.

## Consequences

WorldOS now has a durable operational lifecycle suitable for long-running worlds, controlled stepping, restart continuation, crash recovery, and branch experiments.

The runner is deliberately bounded rather than daemonized. A future service layer may add signals, leases, distributed ownership, and HTTP control without changing the event or recovery contracts defined here.
