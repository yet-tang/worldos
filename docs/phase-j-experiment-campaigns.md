# Phase J — Replicated Experiment Campaigns

Phase I made a single causal experiment reproducible, auditable, and safe to evaluate after outcomes diverge. Phase J moves WorldOS from **one valid trial** to **replicated causal campaigns** across multiple deterministic seeds.

## Why this phase exists

A single deterministic world can establish a mechanism, but it cannot show whether an effect is robust to different initial populations and microstates. WorldOS needs a first-class way to ask:

> If the same intervention is repeated across many independently seeded but protocol-identical worlds, how often does the effect appear, how large is it, and how variable is it?

Phase J deliberately does **not** claim population-level statistical inference. It provides deterministic replication summaries and evidence needed for later statistical tooling.

## Core model

A campaign consists of:

1. one immutable protocol template;
2. a deterministic seed schedule;
3. one treatment/control causal trial per seed;
4. only trials with verified causal attribution entering the effect aggregate;
5. rejected/ineligible trials remaining visible and auditable;
6. deterministic aggregation of numeric outcome deltas and behavior metrics.

## Campaign plan

Inputs:

- `campaign_name`
- `base_seed`
- `trial_count`
- `protocol_template`

The plan deterministically derives trial IDs and seeds from the base seed. Recreating the same plan must produce the same campaign ID, trial IDs, and seeds.

## Trial evidence

Each trial records:

- trial ID and seed;
- causal attestation digest;
- attribution eligibility and attestation verification;
- numeric outcome deltas;
- optional numeric behavioral outcomes;
- source report fingerprint.

Only trials satisfying both `attribution_eligible=true` and `attestation_verified=true` are included in causal aggregation.

## Campaign aggregate

For each metric, report:

- eligible sample count;
- mean;
- median;
- minimum / maximum;
- sample standard deviation;
- positive / negative / zero counts;
- dominant-sign consistency;
- all observed values in deterministic trial order.

The report also exposes rejected trials and reasons. It must never silently discard invalid causal trials.

## Safety and epistemic rules

- Campaign summaries are read-only analytical projections.
- No campaign tool directly mutates production worlds.
- Replication execution still uses ordinary temporary-world MCP/Control tools and Phase I causal attestations.
- A campaign never upgrades an ineligible trial into a causal trial.
- Sign consistency is descriptive evidence, not a p-value or confidence interval.
- Existing protected production worlds remain outside acceptance experiments.

## Phase J acceptance target

Phase J is complete when a production E2E campaign can run the same retain-vs-suppress memory experiment across at least five deterministic seeds and demonstrate:

- identical campaign plan regeneration;
- one independently verified causal attestation per eligible seed;
- invalid/tampered trial exclusion without data loss;
- deterministic campaign summary regeneration;
- per-outcome effect distribution and sign consistency;
- complete cleanup and protected-world zero pollution.
