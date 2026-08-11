# RFC 0035 — Scarcity Social Feedback Loop

## Status
Phase E implementation.

## Goal
Connect existing survival, economy, rumor, relationship, and conflict mechanics so a resource shock can create endogenous social consequences without scripting a predetermined crisis outcome.

## Causal loop

`production shock → personal food-security perception → reserve demand/hoarding → local market pressure → rumor generation/acceptance → higher reserve demand → resource competition → conflict → relationship damage`

Every transition is deterministic and event-audited. A shock does not directly create conflict; conflict requires sufficiently high local pressure and a viable resource-holding target.

## Local knowledge
Actors do not receive global inventory totals. `food_security` is derived from the actor's own food, hunger, known rumors, and a deterministic seed-dependent risk bias. This keeps decision inputs local and makes different world seeds capable of different responses.

## Hoarding
Actors below their target reserve may buy one unit of food from a co-located actor whose inventory exceeds their own target reserve. Price rises with perceived pressure. The action emits `scarcity.purchase` and `decision.evidence`.

This is intentionally a minimal local market, not a global auction.

## Rumors
High food-security pressure can generate a shortage rumor. Rumors spread only among co-located actors and acceptance is gated by relationship trust plus a deterministic seed-dependent threshold. Rejected messages emit `rumor.rejected`; accepted messages emit `rumor.spread`.

`world.stimulus.spread_information` becomes a first domain consumer: its message is seeded into matching actors/locations and can then enter the normal rumor network.

## Conflict
Very high scarcity pressure can create a resource conflict against a co-located actor holding significant food. Existing conflict resolution applies health damage and relationship penalties. The trigger emits `decision.evidence` explaining pressure, relationship, target resources, and chosen severity.

## Production precision
Fractional production is accumulated in a deterministic per-resource carry. This removes truncation bias observed in Phase D: a `-40%` shock to rate 3 now averages 1.8 units/tick over time rather than collapsing permanently to 1 unit/tick.

## Audit events
New/expanded events include:
- `scarcity.perceived`
- `scarcity.purchase`
- `decision.evidence`
- `rumor.generated`
- `rumor.seeded`
- `rumor.spread`
- `rumor.rejected`
- `conflict.resolved` with scarcity reason
- `resource.produced` with exact quantity and production carry

## Non-goals
Phase E does not implement a global price system, firms, credit, formal policing, political institutions, or probabilistic nondeterminism. It also does not guarantee crisis escalation: peaceful recovery is a valid outcome.

## Acceptance
A deterministic A/B resource-shock experiment should be able to show some or all of: production divergence, inventory divergence, scarcity perception, reserve purchases, rumor propagation, relationship change, and conflict. Which effects occur must depend on local conditions and seed rather than a hard-coded story sequence.
