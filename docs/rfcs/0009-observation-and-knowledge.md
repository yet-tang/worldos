# RFC 0009: Observation and Knowledge

Status: Draft

## Summary

Committed world facts are not automatically available to every agent. WorldOS derives observer-specific `observation.created` events from perceivable source events, then projects those observations into mutable beliefs.

```text
World Event
  -> Perception Policy
  -> Observation Event
  -> Belief Event
  -> Knowledge Projection
```

## Invariants

1. The Event Store remains the only source of truth.
2. Observation is derived from a committed event and records `source_event_id`.
3. Knowledge is projected separately from physical world state.
4. Agents read their own beliefs, never unrestricted world state.
5. Perception is deterministic for a given history and policy.
6. Actors and subjects perceive events involving themselves.
7. Bystanders perceive only events allowed by spatial and sensory policy.
8. Beliefs retain source, confidence, subject, and update tick.

## Initial policy

The reference engine supports direct-participant perception and co-located perception for movement, combat, and health events. Future world packages may replace this policy with visibility, sound propagation, concealment, language, deception, and sensor models.
