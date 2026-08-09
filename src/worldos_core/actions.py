from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .events import NewEvent
from .intents import Intent, ValidationIssue, ValidationResult
from .resolution import DeterministicResolver
from .world import EntityProjection, WorldProjection


@dataclass(frozen=True)
class ActionContext:
    timeline_id: str
    state: WorldProjection
    resolver: DeterministicResolver


class ActionRule(Protocol):
    intent_type: str

    def validate(self, intent: Intent, context: ActionContext) -> ValidationResult: ...

    def resolve(self, intent: Intent, context: ActionContext) -> list[NewEvent]: ...


def _entity(state: WorldProjection, entity_id: str | None) -> EntityProjection | None:
    if entity_id is None:
        return None
    return state.entities.get(entity_id)


def _location(entity: EntityProjection | None) -> str | None:
    if entity is None:
        return None
    return entity.components.get("position", {}).get("location_id")


def _positive_int(value: object, default: int) -> int:
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return default


class MoveRule:
    intent_type = "move"

    def validate(self, intent: Intent, context: ActionContext) -> ValidationResult:
        actor = _entity(context.state, intent.actor_id)
        destination = intent.parameters.get("to_location_id")
        issues: list[ValidationIssue] = []
        if actor is None or not actor.active:
            issues.append(ValidationIssue(code="actor_unavailable", message="actor does not exist or is inactive", subject_id=intent.actor_id))
        if not isinstance(destination, str) or not destination:
            issues.append(ValidationIssue(code="destination_required", message="to_location_id is required"))
        if actor is not None and _location(actor) == destination:
            issues.append(ValidationIssue(code="already_there", message="actor is already at destination", subject_id=intent.actor_id))
        return ValidationResult.reject(*issues) if issues else ValidationResult.accept()

    def resolve(self, intent: Intent, context: ActionContext) -> list[NewEvent]:
        intent_id = intent.deterministic_id()
        destination = intent.parameters["to_location_id"]
        correlation_id = intent.correlation_id or intent_id
        return [
            NewEvent(tick=intent.tick, phase="intent", event_type="move.attempted", actor_id=intent.actor_id, subject_ids=(intent.actor_id,), correlation_id=correlation_id, payload={"intent_id": intent_id, "to_location_id": destination}),
            NewEvent(tick=intent.tick, phase="resolution", event_type="move.resolved", actor_id=intent.actor_id, subject_ids=(intent.actor_id,), correlation_id=correlation_id, payload={"intent_id": intent_id, "outcome": "success"}),
            NewEvent(tick=intent.tick, phase="effects", event_type="entity.moved", actor_id=intent.actor_id, subject_ids=(intent.actor_id,), correlation_id=correlation_id, payload={"to_location_id": destination}),
        ]


class AttackRule:
    intent_type = "attack"

    def validate(self, intent: Intent, context: ActionContext) -> ValidationResult:
        actor = _entity(context.state, intent.actor_id)
        target = _entity(context.state, intent.target_id)
        issues: list[ValidationIssue] = []
        if actor is None or not actor.active:
            issues.append(ValidationIssue(code="actor_unavailable", message="actor does not exist or is inactive", subject_id=intent.actor_id))
        if target is None or not target.active:
            issues.append(ValidationIssue(code="target_unavailable", message="target does not exist or is inactive", subject_id=intent.target_id))
        if intent.target_id == intent.actor_id:
            issues.append(ValidationIssue(code="self_target", message="attack target must differ from actor", subject_id=intent.actor_id))
        if actor is not None and target is not None and _location(actor) != _location(target):
            issues.append(ValidationIssue(code="out_of_range", message="actor and target are not co-located", subject_id=intent.target_id))
        return ValidationResult.reject(*issues) if issues else ValidationResult.accept()

    def resolve(self, intent: Intent, context: ActionContext) -> list[NewEvent]:
        intent_id = intent.deterministic_id()
        correlation_id = intent.correlation_id or intent_id
        roll = context.resolver.roll(intent_id=intent_id, channel="attack.hit")
        actor = context.state.entities[intent.actor_id]
        target = context.state.entities[intent.target_id]
        skill = int(actor.components.get("combat", {}).get("skill", 50))
        defense = int(target.components.get("combat", {}).get("defense", 0))
        threshold = max(5, min(95, 50 + skill - defense))
        hit = roll <= threshold
        damage = int(intent.parameters.get("damage", 10)) if hit else 0
        events = [
            NewEvent(tick=intent.tick, phase="intent", event_type="attack.attempted", actor_id=intent.actor_id, subject_ids=(intent.actor_id, intent.target_id), correlation_id=correlation_id, payload={"intent_id": intent_id}),
            NewEvent(tick=intent.tick, phase="resolution", event_type="attack.resolved", actor_id=intent.actor_id, subject_ids=(intent.actor_id, intent.target_id), correlation_id=correlation_id, payload={"intent_id": intent_id, "roll": roll, "threshold": threshold, "outcome": "hit" if hit else "miss", "damage": damage}),
        ]
        if hit:
            events.append(NewEvent(tick=intent.tick, phase="effects", event_type="health.changed", actor_id=intent.actor_id, subject_ids=(intent.target_id,), correlation_id=correlation_id, payload={"delta": -damage, "resolution_roll": roll}))
        return events


class EatRule:
    """Consume owned food to lower hunger through the normal intent pipeline."""

    intent_type = "eat"

    def validate(self, intent: Intent, context: ActionContext) -> ValidationResult:
        actor = _entity(context.state, intent.actor_id)
        issues: list[ValidationIssue] = []
        if actor is None or not actor.active:
            issues.append(ValidationIssue(code="actor_unavailable", message="actor does not exist or is inactive", subject_id=intent.actor_id))
            return ValidationResult.reject(*issues)

        resource = str(intent.parameters.get("resource", "food"))
        quantity = _positive_int(intent.parameters.get("quantity", 1), 1)
        inventory = actor.components.get("inventory", {})
        available = int(inventory.get(resource, 0)) if isinstance(inventory, dict) else 0
        if available < quantity:
            issues.append(ValidationIssue(code="insufficient_food", message=f"not enough {resource} to eat", subject_id=intent.actor_id))
        needs = actor.components.get("needs", actor.components.get("survival", {}))
        hunger = int(needs.get("hunger", 0)) if isinstance(needs, dict) else 0
        if hunger <= 0:
            issues.append(ValidationIssue(code="not_hungry", message="actor is not hungry", subject_id=intent.actor_id))
        return ValidationResult.reject(*issues) if issues else ValidationResult.accept()

    def resolve(self, intent: Intent, context: ActionContext) -> list[NewEvent]:
        actor = context.state.entities[intent.actor_id]
        resource = str(intent.parameters.get("resource", "food"))
        quantity = _positive_int(intent.parameters.get("quantity", 1), 1)
        relief = _positive_int(intent.parameters.get("relief", 45), 45)
        inventory = dict(actor.components.get("inventory", {}))
        inventory[resource] = max(0, int(inventory.get(resource, 0)) - quantity)

        needs = dict(actor.components.get("needs", actor.components.get("survival", {})))
        hunger_before = int(needs.get("hunger", 0))
        hunger_after = max(0, hunger_before - relief * quantity)
        needs["hunger"] = hunger_after
        survival = dict(actor.components.get("survival", needs))
        survival["hunger"] = hunger_after

        intent_id = intent.deterministic_id()
        correlation_id = intent.correlation_id or intent_id
        payload = {
            "intent_id": intent_id,
            "resource": resource,
            "quantity": quantity,
            "hunger_before": hunger_before,
            "hunger_after": hunger_after,
        }
        return [
            NewEvent(tick=intent.tick, phase="intent", event_type="eat.attempted", actor_id=intent.actor_id, subject_ids=(intent.actor_id,), correlation_id=correlation_id, payload={"intent_id": intent_id, "resource": resource, "quantity": quantity}),
            NewEvent(tick=intent.tick, phase="resolution", event_type="eat.resolved", actor_id=intent.actor_id, subject_ids=(intent.actor_id,), correlation_id=correlation_id, payload=payload),
            NewEvent(tick=intent.tick, phase="effects", event_type="entity.component_set", actor_id=intent.actor_id, subject_ids=(intent.actor_id,), correlation_id=correlation_id, payload={"component": "inventory", "value": inventory}),
            NewEvent(tick=intent.tick, phase="effects", event_type="entity.component_set", actor_id=intent.actor_id, subject_ids=(intent.actor_id,), correlation_id=correlation_id, payload={"component": "needs", "value": needs}),
            NewEvent(tick=intent.tick, phase="effects", event_type="entity.component_set", actor_id=intent.actor_id, subject_ids=(intent.actor_id,), correlation_id=correlation_id, payload={"component": "survival", "value": survival}),
        ]


class RestRule:
    """Reduce fatigue through an explicit deterministic self-care action."""

    intent_type = "rest"

    def validate(self, intent: Intent, context: ActionContext) -> ValidationResult:
        actor = _entity(context.state, intent.actor_id)
        issues: list[ValidationIssue] = []
        if actor is None or not actor.active:
            issues.append(ValidationIssue(code="actor_unavailable", message="actor does not exist or is inactive", subject_id=intent.actor_id))
            return ValidationResult.reject(*issues)
        needs = actor.components.get("needs", actor.components.get("survival", {}))
        fatigue = int(needs.get("fatigue", 0)) if isinstance(needs, dict) else 0
        if fatigue <= 0:
            issues.append(ValidationIssue(code="not_tired", message="actor is not tired", subject_id=intent.actor_id))
        return ValidationResult.reject(*issues) if issues else ValidationResult.accept()

    def resolve(self, intent: Intent, context: ActionContext) -> list[NewEvent]:
        actor = context.state.entities[intent.actor_id]
        relief = _positive_int(intent.parameters.get("relief", 40), 40)
        needs = dict(actor.components.get("needs", actor.components.get("survival", {})))
        fatigue_before = int(needs.get("fatigue", 0))
        fatigue_after = max(0, fatigue_before - relief)
        needs["fatigue"] = fatigue_after
        survival = dict(actor.components.get("survival", needs))
        survival["fatigue"] = fatigue_after

        intent_id = intent.deterministic_id()
        correlation_id = intent.correlation_id or intent_id
        return [
            NewEvent(tick=intent.tick, phase="intent", event_type="rest.attempted", actor_id=intent.actor_id, subject_ids=(intent.actor_id,), correlation_id=correlation_id, payload={"intent_id": intent_id}),
            NewEvent(tick=intent.tick, phase="resolution", event_type="rest.resolved", actor_id=intent.actor_id, subject_ids=(intent.actor_id,), correlation_id=correlation_id, payload={"intent_id": intent_id, "fatigue_before": fatigue_before, "fatigue_after": fatigue_after}),
            NewEvent(tick=intent.tick, phase="effects", event_type="entity.component_set", actor_id=intent.actor_id, subject_ids=(intent.actor_id,), correlation_id=correlation_id, payload={"component": "needs", "value": needs}),
            NewEvent(tick=intent.tick, phase="effects", event_type="entity.component_set", actor_id=intent.actor_id, subject_ids=(intent.actor_id,), correlation_id=correlation_id, payload={"component": "survival", "value": survival}),
        ]
