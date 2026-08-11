# Phase E observability notes

Phase E introduces the following durable signals for debugging and A/B experiments:

- `scarcity.perceived`: actor-local food reserve target, shortage, pressure, and rumor pressure
- `scarcity.purchase`: one-unit local reserve purchase, price, pressure, buyer and seller
- `decision.evidence`: structured reason for hoarding or scarcity-driven conflict
- `rumor.generated`: endogenous shortage rumor creation
- `rumor.seeded`: semantic `spread_information` stimulus entering actor rumor state
- `rumor.spread`: trust-gated acceptance
- `rumor.rejected`: trust-gated rejection
- `conflict.resolved.reason=food_scarcity`: endogenous resource competition conflict
- `resource.produced.exact_quantity` and `production_carry`: fractional production accounting

These are audit signals, not narrative conclusions. Consumers should compare timelines and inspect local actor state before attributing causality.
