# Phase E validation scenario

Use a temporary deterministic world only. Keep existing worlds untouched.

1. Create a 10–20 actor agrarian world with low-to-medium initial food abundance and a deterministic seed.
2. Advance 5 ticks and branch from the same point.
3. Apply `resource_shock(food, magnitude=-0.7, duration_ticks=100)` only to the experiment branch.
4. Advance both branches symmetrically and compare at ticks 10, 30, 60, and 105 after the branch.
5. Record production, inventory, average hunger/health, `scarcity.perceived`, `scarcity.purchase`, generated/spread/rejected rumors, decision evidence, relationship changes, and conflicts.
6. Confirm fractional production carry makes long-run produced quantity track the configured modifier rather than integer truncation.
7. Repeat the experiment with the same seed and assert identical canonical hashes/event streams; repeat with at least one different seed and allow a different social outcome.
8. Do not require conflict as a passing condition. A peaceful recovery is valid if local pressure never crosses the endogenous trigger.
9. Delete the temporary world and verify pre-existing worlds are byte/logically unchanged by tick, event count, and canonical hash.
