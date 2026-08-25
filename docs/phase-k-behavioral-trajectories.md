# Phase K — Behavioral Phenotypes and Trajectory Analysis

Phase J established replicated causal campaigns across deterministic seeds. It also exposed the next limitation: endpoint metrics can remain identical even when treatment and control travel through materially different social histories.

Phase K makes those histories first-class analytical objects.

## Core question

Instead of asking only:

> What is different at the end?

Phase K also asks:

> When did the paths first diverge, which behaviors diverged, which actors participated, and how did the divergence unfold over time?

## Behavioral trajectory

A trajectory is a deterministic projection of an event stream over an optional tick window, event-type filter, and actor filter. It records:

- selected event count;
- count by event type;
- participation count by actor, including subjects;
- first and last occurrence of every selected event type;
- ordered behavioral milestones;
- a deterministic trajectory fingerprint.

The projection is read-only and does not mutate worlds.

## Trajectory comparison

Treatment and control trajectories can be compared independently of endpoint state. The comparison reports:

- whether the trajectories are identical;
- first divergent milestone index;
- first divergence tick;
- event-count deltas;
- first-occurrence tick deltas;
- actor-participation deltas;
- deterministic comparison fingerprint.

This allows WorldOS to distinguish cases such as:

- same final food inventory, but one branch experienced an earlier conflict cascade;
- same hunger outcome, but one branch relied on substantially more hoarding;
- same conflict count, but conflicts occurred earlier and involved a different actor set;
- equivalent endpoints reached through different rumor or trading paths.

## Behavioral phenotypes

Phase K adds domain summaries over the same event history. Current first-class phenotypes are:

- `scarcity` — scarcity perception and scarcity purchases;
- `rumor` — generated, spread, and rejected information;
- `conflict` — propensity evidence, conflict decisions, and resolutions;
- `trade` — trade and obligation events;
- `social` — helping and relationship updates.

Each phenotype exposes:

- event count;
- participant count and participant event counts;
- first/last tick;
- active tick span;
- burst tick count;
- peak events per tick;
- deterministic trajectory and phenotype fingerprints.

Treatment/control phenotype comparison additionally exposes deltas for those metrics and can be converted into scalar `phenotype.<name>.*` values suitable for replicated campaign aggregation.

## MCP interface

Phase K exposes four new read-only tools:

- `behavioral_trajectory`
- `compare_behavioral_trajectory`
- `behavioral_phenotype`
- `compare_behavioral_phenotype`

They read branch-local event histories through the same WorldOS inspector path used by other MCP observation tools and never mutate state.

`campaign_trial_result` also accepts optional `phenotype_comparisons`. Their scalar deltas are merged into `behavioral_outcomes`, so Phase J's existing campaign aggregation can compute cross-seed mean, median, range, standard deviation, and sign consistency for trajectory-derived behavior without introducing a second campaign format.

## Causal interpretation

Trajectory divergence is evidence about *how* two causally valid branches evolved; it is not itself sufficient to establish causality. Phase K therefore composes with the Phase H/I causal contract:

1. establish equivalent pre-treatment state;
2. persist/verify the pre-treatment attestation;
3. run the declared intervention;
4. obtain a causally eligible outcome report;
5. inspect trajectory/phenotype divergence;
6. attach phenotype deltas to the verified campaign trial;
7. replicate across deterministic seeds.

If the causal trial is ineligible, Phase J campaign aggregation continues to reject it even when its trajectories differ.

## Production acceptance target

Phase K is complete when production E2E demonstrates all of the following:

1. the four read-only MCP tools are exposed and deterministic;
2. treatment/control first-divergence detection agrees with raw event evidence;
3. scarcity/rumor/conflict/trade/social phenotype summaries agree with raw events;
4. at least one causally valid retain-vs-suppress trial has equal or nearly equal endpoint metrics but auditable behavioral-path divergence;
5. phenotype comparison metrics flow through `campaign_trial_result` and replicated campaign aggregation;
6. re-running the same event histories yields identical trajectory, phenotype, comparison, and campaign fingerprints;
7. invalid causal trials remain excluded even if their behavioral paths diverge;
8. temporary worlds are cleaned and protected production worlds remain unchanged.
