# RFC 0019: Deterministic Survival and Economy Module

## Status

Accepted for WorldOS v1.1.

## Context

The v1.1 runtime can persist history and derive goals from needs, but the physical world still requires a deterministic subsystem that changes survival state and creates social and economic consequences.

## Decision

`SurvivalEconomyModule` runs before cognition on every tick and stages all component changes before emitting events. It provides:

- metabolism: hunger and fatigue increase from per-actor rates;
- survival consequences: maximum hunger or fatigue causes health loss;
- work and production: configured jobs add resources to inventory;
- trade: same-location bilateral offers transfer inventory and money atomically;
- relationships: successful trade improves affinity and conflict reduces it;
- rumors: one stable, previously unknown rumor propagates between co-located actors;
- conflict: configured aggression causes deterministic damage and relationship consequences.

All actors, resources, offers, rumors, and targets are processed in stable lexical order. Values are integer-clamped and the module performs no random sampling or external calls.

## Event model

Authoritative state changes use existing reducers:

- `entity.component_set`
- `health.changed`

Domain audit events are replay-safe no-ops in the physical projection:

- `survival.metabolized`
- `resource.produced`
- `trade.completed`
- `rumor.spread`
- `conflict.resolved`

The audit events remain available to perception, memory, inspection, and narration.

## Component conventions

Characters may expose:

- `needs`: `hunger`, `fatigue`
- `survival`: mirrored survival values
- `metabolism`: per-tick rates
- `health`: current and maximum
- `job`: produced resource and rate
- `inventory`: resource quantities
- `wallet`: integer balance
- `trade_offer`: buyer, resource, quantity, price
- `relationships`: actor affinity from -100 to 100
- `rumors`: stable string facts
- `conflict`: target and severity

## Consequences

This closes the first authoritative living-world loop:

```text
metabolism / work / trade / social events
→ updated physical state
→ needs assessment
→ goal / plan / intent
→ new world effects
```

The current module is intentionally compact. Future modules may split markets, production chains, relationship dynamics, law, and institutions while preserving these deterministic event boundaries.
