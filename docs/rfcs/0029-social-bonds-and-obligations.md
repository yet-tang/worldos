# RFC 0029: Social Bonds and Reciprocity Obligations

## Status

Implemented as the first persistent social-structure layer above character motivation.

## Motivation

A single scalar `relationships[other_id]` is useful as a compatibility signal, but it cannot represent the differences between liking someone, trusting someone, owing them a favor, resenting them, or repeatedly seeing them break commitments.

Without durable social state, a social action affects only the tick in which it occurs. Higher-order systems such as households, partnerships, factions, commerce, romance, reputation, law, and politics would then have to rediscover social history from the event log or invent their own incompatible relationship model.

WorldOS therefore introduces a replayable `SocialProjection` while preserving the existing numeric relationship component for backward compatibility.

## Invariants

1. The event store remains the source of truth.
2. `SocialProjection` is derived only from committed events and is replayable on every timeline and branch.
3. Narrator remains read-only and cannot create, fulfill, or default obligations.
4. Existing `relationships` values remain supported as a compatibility layer; richer social semantics live in `SocialProjection`.
5. Social state is directed. A may trust B more than B trusts A.
6. Affinity, trust, and grievance are independent dimensions.
7. One disagreement or missed favor must not instantly create an enemy.
8. Survival goals continue to preempt non-survival social goals.
9. No pairing, household, faction, romance, marriage, or political outcome is triggered by a fixed tick number.

## SocialBond

A directed bond contains:

- `affinity`: emotional closeness or dislike, range -100..100
- `trust`: expectation that the other person is reliable, range -100..100
- `grievance`: accumulated unresolved resentment, range 0..100
- interaction counters and fulfillment/default history

Derived labels are presentation-level summaries of these dimensions:

- `stranger`
- `acquaintance`
- `friend`
- `ally`
- `rival`
- `enemy`

Labels are not stored as authoritative facts. Replaying the underlying social events must reproduce them.

## Obligations

Two obligation kinds are introduced.

### resource_debt

A resident explicitly asks another resident for a resource and the request is accepted. The transferred resource is a hard debt with a relatively short due window. Default materially reduces trust and the compatibility relationship score and creates grievance.

### favor

A resident voluntarily helps another resident. The help creates a softer reciprocity expectation with a longer window. Failure to reciprocate cools trust slightly but is intentionally insufficient, by itself, to create rivalry or enmity.

This distinction prevents altruism from behaving like an involuntary loan contract.

## Lifecycle

A typical hard-debt chain is:

```text
request resource
  -> request accepted
  -> resource transferred
  -> obligation.created(resource_debt)
  -> debtor later evaluates reciprocity motive
  -> repay_obligation goal
  -> move to creditor if required
  -> social.repaid
  -> obligation.fulfilled
  -> trust increases
```

If repayment does not occur by the due tick:

```text
obligation.created
  -> due tick reached
  -> obligation.defaulted
  -> trust decreases
  -> grievance increases
  -> compatibility relationship decreases
  -> later motivations may react to the resulting rivalry
```

A voluntary favor follows the same replayable lifecycle but uses softer default consequences.

## Motivation integration

Open obligations are candidates in the existing Character Motivation Engine under the `reciprocity` motivation family.

Repayment priority can increase as a deadline approaches and is influenced by existing character drives and social trust. It still competes with other goals and cannot override urgent survival.

The repayment itself goes through the normal runtime path:

```text
Goal -> PlanStep -> Intent -> Validation -> Resolution -> Event Batch -> Projection
```

No direct projection mutation is allowed from motivation or Narrator code.

## Perception and memory

Repayment is a perceivable social action. Participants always perceive events involving themselves, and nearby residents may perceive the repayment as well. Those observations continue through the existing Knowledge and Memory pipeline.

This makes reliability socially visible: a third party can remember that a resident honors commitments, which later systems can use for reputation, hiring, partnership, or faction membership.

## Inspector and Narrator

Actor inspection exposes:

- directed social bonds
- obligations where the actor is debtor
- obligations where the actor is creditor

Actor-perspective Narrator context receives the same derived state. It therefore does not need to reconstruct trust and outstanding commitments by scanning arbitrary historical events.

## Compatibility

Old worlds require no migration or history rewrite. Existing social events replay into the new projection. Residents without social history simply have no derived bonds or obligations until relevant events occur.

The legacy `relationships` component continues to be updated by social actions so existing modules and UI surfaces remain functional during the transition.

## Deferred scope

This RFC intentionally does not define:

- households or kinship
- romance, marriage, or reproduction
- formal friendship declarations
- contracts beyond simple resource reciprocity
- reputation propagation
- businesses or employment contracts
- factions, leadership, voting, law, crime, or punishment

Those systems should be built on top of this directed trust/grievance/obligation layer rather than introducing separate relationship stores.

## Acceptance criteria

- Social projection replay is deterministic.
- Helping produces a soft favor obligation.
- An accepted resource request produces a hard resource debt.
- A capable debtor can autonomously select and execute a repayment goal.
- Fulfillment changes trust and is observable by nearby residents.
- A hard default creates meaningful grievance without immediately requiring an enemy label.
- A missed voluntary favor has substantially softer consequences than a hard debt default.
- Inspector and actor-perspective Narrator expose bonds and obligations.
- Existing Python matrix, 10,000-tick persistence acceptance, and container smoke remain green.
