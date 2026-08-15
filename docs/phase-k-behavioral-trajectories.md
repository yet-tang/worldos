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

## Phase K direction

The initial kernel intentionally remains event-type agnostic. It preserves raw event semantics rather than hard-coding one crisis model. Subsequent commits will add:

1. first-class MCP trajectory inspection/comparison;
2. phenotype summaries for scarcity, hoarding, rumor, conflict, trade, and social-network participation;
3. trajectory deltas as optional Phase J campaign evidence;
4. replicated phenotype distributions across seeds;
5. production E2E acceptance using retain-vs-suppress experiments where endpoint metrics are zero but paths diverge.

## Acceptance target

Phase K is complete when production E2E can demonstrate a causally valid treatment/control experiment where endpoint metrics are equal or nearly equal, while WorldOS deterministically identifies and audits meaningful trajectory divergence from the underlying event history.
