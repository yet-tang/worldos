# RFC 0013: World Module Interface

Status: Draft

## Summary

WorldOS world subsystems such as physics, economy, society, and politics execute through a deterministic module contract owned by the tick engine. Modules may propose events, but they never mutate projections or the event store directly.

## Contract

A module has a unique `name`, an integer `order`, and two hooks:

- `before_actions(context)` runs after `tick.started` and before agent planning.
- `after_actions(context, action_events)` runs after agent actions and before perception.

The registry orders modules by `(order, name)`. Every emitted event must target the active tick. The runtime adds `module` and `module_hook` metadata for auditability.

## Invariants

1. Modules are deterministic functions of their input context.
2. Modules cannot append events directly.
3. Module names are unique within one engine.
4. Event ordering is stable across replay.
5. Cross-module communication occurs through committed events and projections, not shared mutable state.
6. Module events pass through the same atomic event-store append path as all authoritative history.

## Rationale

This boundary lets WorldOS add physical, economic, social, and political simulation without coupling those domains to agents or the narrator. It also preserves replay, branching, inspection, and deterministic testing.
