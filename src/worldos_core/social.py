from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import BaseModel, Field

from .events import Event, NewEvent
from .world import EntityProjection, WorldProjection

ObligationKind = Literal["resource_debt", "favor"]
ObligationStatus = Literal["open", "fulfilled", "defaulted"]


class SocialBond(BaseModel):
    actor_id: str
    other_id: str
    affinity: int = 0
    trust: int = 0
    grievance: int = 0
    interactions: int = 0
    helps_received: int = 0
    obligations_fulfilled: int = 0
    obligations_defaulted: int = 0

    def label(self) -> str:
        if self.grievance >= 12 or self.affinity <= -25:
            return "enemy"
        if self.trust >= 28 and self.affinity >= 16:
            return "ally"
        if self.affinity >= 20 and self.trust >= 10:
            return "friend"
        if self.interactions >= 2:
            return "acquaintance"
        return "stranger"


class SocialObligation(BaseModel):
    obligation_id: str
    debtor_id: str
    creditor_id: str
    kind: ObligationKind
    resource: str = "food"
    quantity: int = 1
    created_tick: int
    due_tick: int
    status: ObligationStatus = "open"
    resolved_tick: int | None = None
    source_correlation_id: str | None = None


class SocialProjection(BaseModel):
    bonds_by_actor: dict[str, dict[str, SocialBond]] = Field(default_factory=dict)
    obligations: dict[str, SocialObligation] = Field(default_factory=dict)
    applied_event_ids: list[str] = Field(default_factory=list)

    def bond(self, actor_id: str, other_id: str) -> SocialBond:
        return self.bonds_by_actor.get(actor_id, {}).get(
            other_id,
            SocialBond(actor_id=actor_id, other_id=other_id),
        )

    def open_obligations_for_debtor(self, actor_id: str) -> list[SocialObligation]:
        return sorted(
            [
                item
                for item in self.obligations.values()
                if item.debtor_id == actor_id and item.status == "open"
            ],
            key=lambda item: (item.due_tick, item.created_tick, item.obligation_id),
        )

    def open_obligations_for_creditor(self, actor_id: str) -> list[SocialObligation]:
        return sorted(
            [
                item
                for item in self.obligations.values()
                if item.creditor_id == actor_id and item.status == "open"
            ],
            key=lambda item: (item.due_tick, item.created_tick, item.obligation_id),
        )


SOCIAL_EVENT_TYPES = {
    "social.interacted",
    "social.helped",
    "social.request_resolved",
    "social.confronted",
    "social.repaid",
    "obligation.created",
    "obligation.fulfilled",
    "obligation.defaulted",
}


def reduce_social(state: SocialProjection, event: Event) -> SocialProjection:
    if event.event_type not in SOCIAL_EVENT_TYPES:
        return state

    next_state = state.model_copy(deep=False)
    next_state.bonds_by_actor = dict(state.bonds_by_actor)
    next_state.obligations = state.obligations
    next_state.applied_event_ids = [*state.applied_event_ids, event.event_id]

    if event.event_type == "obligation.created":
        obligation = SocialObligation(**event.payload)
        if obligation.obligation_id in state.obligations:
            return state
        obligations = dict(state.obligations)
        obligations[obligation.obligation_id] = obligation
        next_state.obligations = obligations
        return next_state

    if event.event_type in {"obligation.fulfilled", "obligation.defaulted"}:
        obligation_id = str(event.payload["obligation_id"])
        current = state.obligations.get(obligation_id)
        if current is None or current.status != "open":
            return state
        status: ObligationStatus = "fulfilled" if event.event_type == "obligation.fulfilled" else "defaulted"
        obligations = dict(state.obligations)
        obligations[obligation_id] = current.model_copy(
            update={"status": status, "resolved_tick": event.tick}
        )
        next_state.obligations = obligations
        if status == "fulfilled":
            _adjust_bond(next_state, current.creditor_id, current.debtor_id, trust=4, affinity=2, fulfilled=1)
            _adjust_bond(next_state, current.debtor_id, current.creditor_id, trust=8, affinity=3, fulfilled=1)
        else:
            _adjust_bond(next_state, current.creditor_id, current.debtor_id, trust=-16, affinity=-6, grievance=12, defaulted=1)
            _adjust_bond(next_state, current.debtor_id, current.creditor_id, trust=-5, affinity=-3, grievance=4, defaulted=1)
        return next_state

    actor_id = event.actor_id or (event.subject_ids[0] if event.subject_ids else None)
    target_id = str(event.payload.get("target_id") or (event.subject_ids[1] if len(event.subject_ids) > 1 else ""))
    if not actor_id or not target_id:
        return next_state

    if event.event_type == "social.interacted":
        _adjust_bond(next_state, actor_id, target_id, affinity=3, trust=1, interactions=1)
        _adjust_bond(next_state, target_id, actor_id, affinity=3, trust=1, interactions=1)
    elif event.event_type == "social.helped":
        _adjust_bond(next_state, actor_id, target_id, affinity=3, trust=2, interactions=1)
        _adjust_bond(next_state, target_id, actor_id, affinity=6, trust=9, interactions=1, helps_received=1)
    elif event.event_type == "social.request_resolved":
        accepted = event.payload.get("outcome") == "accepted"
        if accepted:
            _adjust_bond(next_state, actor_id, target_id, affinity=2, trust=4, interactions=1)
            _adjust_bond(next_state, target_id, actor_id, affinity=1, trust=2, interactions=1)
        else:
            _adjust_bond(next_state, actor_id, target_id, affinity=-2, trust=-2, grievance=2, interactions=1)
            _adjust_bond(next_state, target_id, actor_id, affinity=-1, interactions=1)
    elif event.event_type == "social.confronted":
        _adjust_bond(next_state, actor_id, target_id, affinity=-6, trust=-5, grievance=7, interactions=1)
        _adjust_bond(next_state, target_id, actor_id, affinity=-5, trust=-4, grievance=6, interactions=1)
    elif event.event_type == "social.repaid":
        _adjust_bond(next_state, actor_id, target_id, affinity=4, trust=7, interactions=1)
        _adjust_bond(next_state, target_id, actor_id, affinity=5, trust=10, interactions=1)
    return next_state


def replay_social(events: list[Event], initial: SocialProjection | None = None) -> SocialProjection:
    state = initial.model_copy(deep=True) if initial else SocialProjection()
    for event in events:
        state = reduce_social(state, event)
    return state


class SocialStructureEngine:
    """Creates reciprocity obligations and turns broken ones into durable consequences."""

    resource_debt_due = 8
    favor_due = 12

    def derive_after_actions(
        self,
        social: SocialProjection,
        source_events: list[Event],
        *,
        tick: int,
    ) -> list[NewEvent]:
        events: list[NewEvent] = []
        known = set(social.obligations)
        for source in source_events:
            if source.event_type == "social.helped":
                creditor_id = source.actor_id or str(source.payload.get("helper_id", ""))
                debtor_id = str(source.payload.get("target_id", ""))
                kind: ObligationKind = "favor"
                due_tick = tick + self.favor_due
            elif source.event_type == "social.request_resolved" and source.payload.get("outcome") == "accepted":
                debtor_id = source.actor_id or (source.subject_ids[0] if source.subject_ids else "")
                creditor_id = str(source.payload.get("target_id", ""))
                kind = "resource_debt"
                due_tick = tick + self.resource_debt_due
            else:
                continue
            if not debtor_id or not creditor_id or debtor_id == creditor_id:
                continue
            resource = str(source.payload.get("resource", "food"))
            quantity = max(1, int(source.payload.get("quantity", 1)))
            obligation_id = self._obligation_id(source, debtor_id, creditor_id, resource, quantity)
            if obligation_id in known:
                continue
            known.add(obligation_id)
            events.append(
                NewEvent(
                    tick=tick,
                    phase="social",
                    event_type="obligation.created",
                    actor_id=debtor_id,
                    subject_ids=(debtor_id, creditor_id),
                    correlation_id=source.correlation_id or obligation_id,
                    caused_by=(source.event_id,),
                    payload={
                        "obligation_id": obligation_id,
                        "debtor_id": debtor_id,
                        "creditor_id": creditor_id,
                        "kind": kind,
                        "resource": resource,
                        "quantity": quantity,
                        "created_tick": tick,
                        "due_tick": due_tick,
                        "status": "open",
                        "source_correlation_id": source.correlation_id,
                    },
                )
            )
        return events

    def derive_deadlines(
        self,
        social: SocialProjection,
        world: WorldProjection,
        *,
        tick: int,
    ) -> list[NewEvent]:
        events: list[NewEvent] = []
        for obligation in sorted(social.obligations.values(), key=lambda item: item.obligation_id):
            if obligation.status != "open" or tick < obligation.due_tick:
                continue
            events.append(
                NewEvent(
                    tick=tick,
                    phase="social",
                    event_type="obligation.defaulted",
                    actor_id=obligation.debtor_id,
                    subject_ids=(obligation.debtor_id, obligation.creditor_id),
                    correlation_id=obligation.source_correlation_id or obligation.obligation_id,
                    payload={
                        "obligation_id": obligation.obligation_id,
                        "debtor_id": obligation.debtor_id,
                        "creditor_id": obligation.creditor_id,
                        "reason": "unfulfilled_by_due_tick",
                    },
                )
            )
            debtor = world.entities.get(obligation.debtor_id)
            creditor = world.entities.get(obligation.creditor_id)
            if debtor is not None:
                events.append(
                    _relationship_effect(
                        debtor,
                        obligation.creditor_id,
                        -5,
                        tick=tick,
                        actor_id=obligation.debtor_id,
                        correlation_id=obligation.obligation_id,
                    )
                )
            if creditor is not None:
                events.append(
                    _relationship_effect(
                        creditor,
                        obligation.debtor_id,
                        -10,
                        tick=tick,
                        actor_id=obligation.creditor_id,
                        correlation_id=obligation.obligation_id,
                    )
                )
        return events

    @staticmethod
    def _obligation_id(
        source: Event,
        debtor_id: str,
        creditor_id: str,
        resource: str,
        quantity: int,
    ) -> str:
        base = source.correlation_id or source.event_id
        digest = hashlib.sha256(
            f"{base}:{debtor_id}:{creditor_id}:{resource}:{quantity}".encode("utf-8")
        ).hexdigest()[:20]
        return f"obl_{digest}"


def _adjust_bond(
    state: SocialProjection,
    actor_id: str,
    other_id: str,
    *,
    affinity: int = 0,
    trust: int = 0,
    grievance: int = 0,
    interactions: int = 0,
    helps_received: int = 0,
    fulfilled: int = 0,
    defaulted: int = 0,
) -> None:
    actor_bonds = dict(state.bonds_by_actor.get(actor_id, {}))
    current = actor_bonds.get(other_id, SocialBond(actor_id=actor_id, other_id=other_id))
    actor_bonds[other_id] = current.model_copy(
        update={
            "affinity": _clamp(current.affinity + affinity),
            "trust": _clamp(current.trust + trust),
            "grievance": max(0, min(100, current.grievance + grievance)),
            "interactions": current.interactions + interactions,
            "helps_received": current.helps_received + helps_received,
            "obligations_fulfilled": current.obligations_fulfilled + fulfilled,
            "obligations_defaulted": current.obligations_defaulted + defaulted,
        }
    )
    state.bonds_by_actor[actor_id] = actor_bonds


def _relationship_effect(
    entity: EntityProjection,
    other_id: str,
    delta: int,
    *,
    tick: int,
    actor_id: str,
    correlation_id: str,
) -> NewEvent:
    raw = entity.components.get("relationships", {})
    relationships = dict(raw) if isinstance(raw, dict) else {}
    relationships[other_id] = _clamp(int(relationships.get(other_id, 0)) + delta)
    return NewEvent(
        tick=tick,
        phase="effects",
        event_type="entity.component_set",
        actor_id=actor_id,
        subject_ids=(entity.entity_id,),
        correlation_id=correlation_id,
        payload={"component": "relationships", "value": relationships},
    )


def _clamp(value: int) -> int:
    return max(-100, min(100, int(value)))
