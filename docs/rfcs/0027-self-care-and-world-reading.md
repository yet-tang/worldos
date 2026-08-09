# RFC 0027: Self-care loop and world-reading surface

## Status

Accepted for the development runtime.

## Problem

Long-running created worlds exposed two related failures:

1. a character could reach hunger 100 and fatigue 100 while continuing automatic job production every tick;
2. the Inspector translated those low-level events into Chinese but still displayed them one by one, hiding the character's actual situation behind bookkeeping noise.

The runtime cause was structural. Created characters had `needs` but no explicit self-care policy, `NeedEngine` defaulted unknown needs to a `survive` goal, the reference planner had no eat/rest steps for that goal, and the intent pipeline had no eat/rest rules. Automatic production was independent of survival condition.

## Runtime invariant

Basic biological needs must be able to close through the normal deterministic decision pipeline:

```text
metabolism
  -> need assessment
  -> explicit goal
  -> plan step
  -> intent
  -> validation/resolution
  -> canonical component events
```

For the reference runtime:

- hunger >= 70 creates an `eat` goal;
- fatigue >= 75 creates a `rest` goal;
- eating consumes owned food and reduces hunger;
- resting reduces fatigue;
- old active hunger/fatigue `survive` goals are suspended so existing development worlds can migrate naturally on their next tick;
- once the corresponding need drops below its threshold, its active self-care goal is suspended;
- automatic job production is suppressed while hunger or fatigue is at/above its work limit;
- a character whose health reaches zero is deactivated.

`eat.resolved` and `rest.resolved` are audit events. Canonical world mutation continues to be represented by ordinary `entity.component_set` events so replay and branching keep the same event-sourced semantics.

## Presentation invariant

The normal Inspector surface is a world-reading product, not an event debugger.

Routine state bookkeeping must therefore be summarized into:

- current situation;
- survival warnings;
- recent production totals;
- health trend;
- latest body state;
- latest meal/rest;
- important experiences such as rumors, trades, conflicts, movement, and deactivation.

The complete event and resident payloads remain available in raw-data disclosures for debugging. Presentation aggregation must never delete or rewrite persisted history.

## Compatibility

The self-care defaults live in `NeedEngine`, not only in World Creator bootstrap data. This is intentional: worlds created before this RFC gain the fixed behavior on their next tick without rewriting their historical events.
