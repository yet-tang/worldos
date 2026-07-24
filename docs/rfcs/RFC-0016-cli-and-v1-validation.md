# RFC-0016: CLI and v1 Validation Boundary

Status: Accepted

## Purpose

WorldOS v1 needs an executable acceptance surface that proves the kernel can be used without importing private implementation details. The CLI is a thin adapter over public runtime, inspector, and narrator APIs; it is not a second mutation path.

## Commands

- `worldos-core demo`: demonstrate replay and Timeline branching.
- `worldos-core simulate`: bootstrap a deterministic world and execute Tick Engine cycles.
- `worldos-core inspect`: expose one actor's replay-backed debug view.
- `worldos-core narrate`: expose omniscient or actor-scoped read-only narrative context.

All commands use an in-memory Event Store and serialize stable JSON output.

## Invariants

1. Simulation commands advance the world only through `DeterministicTickEngine` or explicit bootstrap events.
2. Inspector and Narrator commands are read-only.
3. A fixed seed and identical bootstrap history produce identical committed events and world hashes.
4. Actor-scoped narration must preserve the Observation / Belief boundary.
5. CLI output must be valid JSON so it can serve as an integration contract.
6. A failing CLI smoke test fails CI.

## Continuous Integration

The v1 baseline is tested on all supported Python minors. CI must:

1. install the package with development dependencies;
2. execute the complete pytest suite;
3. execute simulation, inspection, and narration smoke tests.

## v1 Acceptance Scope

The v1 runtime is considered technically complete only when the following are present and passing together:

- event-sourced kernel and replay;
- Timeline branching;
- deterministic Scheduler / Tick Engine;
- Intent validation and resolution;
- Observation / Knowledge projection;
- layered Memory architecture;
- Goal / Planner runtime;
- World Module interface;
- Inspector / Debug API;
- Narrator read-only API;
- CLI examples;
- end-to-end tests and CI.

Passing isolated milestone tests is insufficient. The end-to-end test must demonstrate Goal → Plan → Intent → World Effect → Observation → Belief → Memory in one committed Timeline.
