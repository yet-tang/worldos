# RFC 0028 — Character Motivation and Emergent Story Loop

Status: Accepted for development baseline

## 1. Purpose

WorldOS must not depend on scripted plot triggers to create story. A story is an interpretation of causal world history: characters perceive conditions, form motives, choose goals, act, change the world, and create new conditions for themselves and other residents.

This RFC defines the first deterministic motivation and social-action layer above basic survival.

## 2. Core loop

```text
World state
  → perception / memory / relationships
  → survival needs + long-term drives + personality
  → motivation candidates
  → priority competition
  → selected Goal
  → Plan
  → Intent
  → Validation / Resolution
  → Event batch
  → world / relationship / resource changes
  → perception by participants and bystanders
  → beliefs / memories
  → later motivation
```

The Narrator remains read-only. It may summarize this loop but may not manufacture world facts or trigger a plot.

## 3. Character profile

Characters may carry two durable components:

- `personality`: sociability, generosity, assertiveness, risk tolerance.
- `drives`: security, belonging, status, wealth, curiosity.

If an older world has no profile, the runtime materializes one through normal `entity.component_set` events. Defaults are deterministic from world seed + actor ID, so replay remains deterministic while identical actor IDs in different worlds need not have identical personalities.

World creation does not require a history rewrite or migration.

## 4. Survival preemption

Basic self-care has priority over ordinary social motivation.

- hunger >= 70 preempts non-survival goals;
- fatigue >= 75 preempts non-survival goals;
- non-survival motivation priorities are capped below the urgent self-care range.

A resident must not choose status, belonging, care, or curiosity over immediate survival.

## 5. Candidate motivations

The first baseline supports:

- **security** → request food from a resident with surplus before starvation is critical;
- **care** → a generous resident may give food to a hungry resident;
- **belonging** → seek interaction with a weak or neutral social tie;
- **status** → confront an existing rival non-violently;
- **curiosity** → explore another populated location.

This is intentionally a small extensible set, not an exhaustive list of human behavior.

Each candidate has a deterministic priority, parameters, and a human-readable reason. The engine may emit `motivation.considered` and `motivation.selected` audit events. These events are developer evidence, not ordinary user-facing world events.

## 6. Cadence and cooldown

Characters do not reconsider every social desire every tick.

- evaluation is staggered deterministically across actors;
- the current baseline evaluates a resident on a three-tick cadence;
- recently pursued motivation categories have a cooldown window;
- only one active motivation-origin goal is maintained per actor at a time.

This prevents social event storms while still allowing the society to evolve.

## 7. Social actions

All actions go through the normal Intent Pipeline. The motivation layer never directly mutates world state.

Initial social actions:

- `request_resource`;
- `help_resident`;
- `socialize`;
- `confront`.

Targeted social plans may first move the actor to the target's current location. Resolution emits semantic audit events such as `social.helped` or `social.request_resolved`; durable consequences use normal world events such as `entity.component_set` and `entity.moved`.

## 8. Consequences

Social actions may change:

- inventories;
- bilateral relationship values;
- rumor knowledge;
- character location.

A rejected request is still a completed social attempt and may reduce a relationship. Helping may improve trust. Confrontation may worsen a rivalry. These consequences are intended to alter later motivation scores.

## 9. Observation and memory

Participants always perceive their own social interaction. Nearby residents may perceive audible social events. Perceived events flow through the existing Observation → Belief → Memory pipeline.

The story loop therefore has causal persistence: a social act can be remembered by someone who was not one of the two principals.

## 10. Goal lifecycle

A selected motivation goal must terminate.

- successful final step → goal `completed`;
- rejected/failed action → goal `failed`;
- an unplannable motivation goal → goal `failed`;
- survival policy may suspend obsolete self-care goals independently.

Completed/failed motivation goals remain in history and participate in cooldown checks.

## 11. Presentation boundary

Normal Inspector surfaces should show:

- personality and long-term drives;
- current active/recent goals;
- motive/reason for a goal;
- important social consequences and memories.

Internal candidate scoring and technical event types remain available in raw/debug data but should not dominate the ordinary world-reading surface.

## 12. Non-goals

This RFC does not yet provide:

- families, romance, marriage, children;
- law, institutions, elections, factions;
- explicit work scheduling or careers;
- stealing, deception, promises, debt, contracts;
- full market pricing and supply chains;
- LLM-authored decisions;
- a scripted quest/story system.

Those should be layered onto the same causal contract rather than bypassing it.

## 13. Determinism invariant

Given the same initial event history, world seed, and runtime version, motivation candidates, selected goals, social resolution rolls, events, and resulting world projections must be identical.
