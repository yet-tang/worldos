# RFC 0036 — Adaptive Memory and Social Structure

## Status
Phase F implementation.

## Goal
WorldOS actors should not react to each crisis as if it were their first. Salient lived events become durable episodic memories; repeated experience changes reserve targets, rumor acceptance, conflict caution, partner choice, and stable social structure.

## Experience memory
The adaptive module records deterministic episodic memories for salient events from the prior completed tick:

- scarcity perception and scarcity purchases
- rumor generation, spread, and rejection
- trade
- conflict
- help
- fulfilled/defaulted obligations

Each memory points to its source event and preserves the source payload. Conflict and broken obligations receive higher salience than routine signals.

## Adaptive strategy
For each actor, active experience memories are summarized into a world-visible `adaptive_strategy` component:

- `reserve_bonus`: learned tendency to hold more food after repeated scarcity/hoarding
- `rumor_skepticism`: higher evidence/trust requirement after repeated rejected rumors and conflict
- `conflict_caution`: learned reluctance to escalate after prior conflicts
- `reciprocity_bias`: durable response to fulfilled/defaulted obligations
- `preferred_partners`: counterparties associated with successful trade/help/repayment
- `avoided_partners`: counterparties associated with conflict/default

The component includes an evidence summary so every learned strategy remains explainable.

## Social structure
A `social_structure` component summarizes stable local structure rather than only momentary relationship numbers:

- trusted circle
- avoidance circle
- network stability

It combines current relationships with learned partner preferences and avoidance.

## Domain effects
The survival/economy module consumes the prior tick's adaptive strategy:

1. prior scarcity increases target food reserve;
2. preferred partners are chosen first for scarcity purchases and avoided partners are skipped;
3. rumor skepticism raises the trust threshold for accepting new rumors;
4. conflict caution raises the escalation threshold.

Adaptive state applies on subsequent ticks, preserving deterministic replay and preventing same-tick circular causality.

## Design boundary
Learning changes propensities, not guaranteed outcomes. A prior famine does not force hoarding, a prior conflict does not guarantee pacifism, and a trusted partner is only preferred when actually available.

## Primary validation
The core Phase F experiment is a repeated-crisis A/B test:

1. create two identical branches;
2. expose one branch to an initial food crisis and allow recovery;
3. expose both branches to an identical second crisis;
4. compare reserve targets, purchase timing, rumor acceptance, partner choice, conflict onset, social structure, health, and inventory.

The hypothesis is not that the experienced society must always outperform the naive society. The required property is path dependence: the first crisis must be able to change behavior during the second while replay remains deterministic.
