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
4. one Phase I historical attestation per eligible trial;
5. only verified, protocol-matching causal trials entering the aggregate;
6. rejected/ineligible/drifted trials remaining visible and auditable;
7. deterministic aggregation of numeric outcome deltas and behavior metrics.

## Campaign plan

Inputs:

- `campaign_name`
- `base_seed`
- `trial_count`
- `protocol_template`

The plan deterministically derives trial IDs and seeds from the base seed. Recreating the same plan must produce the same campaign ID, trial IDs, and seeds.

The protocol template may contain broader execution metadata, but the campaign analyzer can directly verify these causal-report fields:

- `treatment_intervention` (alias: `treatment`)
- `control_intervention` (alias: `control`)
- `outcome_names`

The observed treatment/control interventions and selected-outcome names are fingerprinted for every trial. A trial whose observed protocol does not match the campaign template is rejected from the causal aggregate even if its own attestation is otherwise valid.

## Trial evidence

Each trial records:

- trial ID and deterministic campaign seed;
- causal attestation digest;
- attribution eligibility and attestation verification;
- protocol-match state and observed protocol fingerprint;
- numeric outcome deltas;
- optional numeric behavioral outcomes;
- source evidence fingerprint.

Only trials satisfying all of the following enter causal aggregation:

- `attribution_eligible=true`
- `attestation_verified=true`
- `protocol_match=true`
- campaign seed matches the plan
- observed protocol fingerprint matches the verifiable portion of the campaign template when such a template is declared

Missing, invalid, seed-mismatched, protocol-drifted, or tampered trials remain visible with rejection reasons.

## Outcome normalization

Phase I causal reports can expose nested numeric outcomes such as:

```text
inventory_totals:
  food: -42
  wood: 3
```

Phase J turns numeric leaves into deterministic dotted metrics:

```text
inventory_totals.food = -42
inventory_totals.wood = 3
```

Non-numeric diagnostic values and booleans are not coerced into campaign metrics.

## Campaign aggregate

For each metric, report:

- eligible sample count;
- mean;
- median;
- minimum / maximum;
- sample standard deviation;
- positive / negative / zero counts;
- dominant sign;
- dominant-sign consistency;
- all observed values in deterministic trial order.

If multiple signs tie for the largest count, `dominant_sign` is `mixed`; the implementation does not choose an arbitrary sign.

The report also exposes rejected trials and reasons. It must never silently discard invalid causal trials.

## MCP surface

Phase J adds three read-only analytical tools:

### `plan_experiment_campaign`

Builds a deterministic campaign ID, trial IDs, and seed schedule from the campaign specification. It does not create worlds.

### `campaign_trial_result`

Normalizes one Phase I causal report plus optional behavioral outcomes into auditable campaign evidence. It preserves attestation eligibility/verification and fingerprints the observed causal protocol.

### `summarize_experiment_campaign`

Validates the campaign plan and submitted trial evidence, rejects invalid or drifted trials, and produces deterministic replication summaries.

Actual treatment/control execution still uses the ordinary WorldOS world, branch, intervention, stimulus, advance, attestation, and causal-report tools. This keeps campaign analytics read-only while preserving existing event-sourcing and idempotency boundaries.

## Safety and epistemic rules

- Campaign tools are read-only analytical projections.
- No campaign tool directly mutates production worlds.
- Replication execution still uses ordinary temporary-world MCP/Control tools and Phase I causal attestations.
- A campaign never upgrades an ineligible trial into a causal trial.
- A campaign never silently aggregates a protocol-drifted trial.
- Sign consistency is descriptive evidence, not a p-value, confidence interval, or population estimate.
- Existing protected production worlds remain outside acceptance experiments.

## Phase J acceptance target

Phase J is complete when a production E2E campaign can run the same retain-vs-suppress memory experiment across at least five deterministic seeds and demonstrate:

- identical campaign plan regeneration;
- unique deterministic trial seeds;
- one independently verified historical causal attestation per eligible seed;
- protocol-identical treatment/control definitions across eligible trials;
- invalid/tampered/protocol-drifted trial exclusion without data loss;
- nested numeric outcome normalization;
- deterministic campaign summary regeneration;
- per-outcome and behavioral effect distributions with sign consistency;
- complete cleanup and protected-world zero pollution.