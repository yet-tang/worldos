# RFC 0022: First Living World

## Status

Accepted for WorldOS v1.1.

## Goal

Provide one executable, persistent scenario proving that the WorldOS kernel can host a small deterministic society rather than isolated unit examples.

## Scenario

The reference world contains exactly three locations (`farm`, `market`, and `homes`) and twelve residents. Residents have health, hunger, fatigue, jobs, inventories, wallets, relationships, rumors, and identities. Bootstrap data includes one valid trade, one conflict, and one rumor source so the survival/economy module demonstrates production, exchange, relationship changes, information spread, and consequences.

## Determinism

The same bootstrap history, seed, and tick count must produce the same canonical world hash and event count, including when execution is interrupted by a process restart.

## Persistence acceptance

The scenario must:

1. initialize idempotently in SQLite;
2. run through `WorldRunner` with snapshots;
3. close and reopen midway without changing the resulting world;
4. branch from the restart checkpoint while preserving the source timeline;
5. expose omniscient and resident-scoped Narrator contexts;
6. replay a 10,000-tick durable history in CI.

The long-run CI guard deactivates residents before advancing the clock. Behavioral integration is tested separately over active ticks; this keeps the durability test bounded while still verifying 10,000 committed ticks, snapshots, restart, and full replay.

## CLI

```bash
worldos-living init --db living.db
worldos-living run --db living.db --ticks 10000 --restart-at 5000
worldos-inspector --db living.db
```

The run command emits a machine-readable report containing world and branch hashes, event counts, restart verification, actor and location counts, narrator visibility counts, and runner metrics.

## Non-goals

This reference scenario is not a balanced game economy, a realistic demographic model, or an LLM-driven society. Its purpose is deterministic end-to-end acceptance and a stable base for future world content.
