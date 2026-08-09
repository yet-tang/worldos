from __future__ import annotations

from .actions import ActionContext
from .events import NewEvent
from .intents import Intent, ValidationIssue, ValidationResult


class RepayObligationRule:
    """Repay a resource-based social obligation through the normal intent pipeline."""

    intent_type = "repay_obligation"

    def validate(self, intent: Intent, context: ActionContext) -> ValidationResult:
        actor = context.state.entities.get(intent.actor_id)
        target = context.state.entities.get(intent.target_id or "")
        issues: list[ValidationIssue] = []
        if actor is None or not actor.active:
            issues.append(
                ValidationIssue(
                    code="actor_unavailable",
                    message="actor does not exist or is inactive",
                    subject_id=intent.actor_id,
                )
            )
        if target is None or not target.active:
            issues.append(
                ValidationIssue(
                    code="target_unavailable",
                    message="creditor does not exist or is inactive",
                    subject_id=intent.target_id,
                )
            )
        if intent.target_id == intent.actor_id:
            issues.append(
                ValidationIssue(
                    code="self_target",
                    message="creditor must differ from debtor",
                    subject_id=intent.actor_id,
                )
            )
        if actor is not None and target is not None:
            actor_location = actor.components.get("position", {}).get("location_id")
            target_location = target.components.get("position", {}).get("location_id")
            if actor_location != target_location:
                issues.append(
                    ValidationIssue(
                        code="out_of_range",
                        message="debtor and creditor are not co-located",
                        subject_id=intent.target_id,
                    )
                )
            resource = str(intent.parameters.get("resource", "food"))
            quantity = max(1, int(intent.parameters.get("quantity", 1)))
            inventory = actor.components.get("inventory", {})
            available = int(inventory.get(resource, 0)) if isinstance(inventory, dict) else 0
            if available < quantity:
                issues.append(
                    ValidationIssue(
                        code="insufficient_resource",
                        message=f"not enough {resource} to repay obligation",
                        subject_id=intent.actor_id,
                    )
                )
        obligation_id = intent.parameters.get("obligation_id")
        if not isinstance(obligation_id, str) or not obligation_id:
            issues.append(ValidationIssue(code="obligation_required", message="obligation_id is required"))
        return ValidationResult.reject(*issues) if issues else ValidationResult.accept()

    def resolve(self, intent: Intent, context: ActionContext) -> list[NewEvent]:
        actor = context.state.entities[intent.actor_id]
        target = context.state.entities[intent.target_id]
        obligation_id = str(intent.parameters["obligation_id"])
        resource = str(intent.parameters.get("resource", "food"))
        quantity = max(1, int(intent.parameters.get("quantity", 1)))

        actor_inventory = dict(actor.components.get("inventory", {}))
        target_inventory = dict(target.components.get("inventory", {}))
        actor_inventory[resource] = int(actor_inventory.get(resource, 0)) - quantity
        target_inventory[resource] = int(target_inventory.get(resource, 0)) + quantity

        actor_relationships = _relationship_delta(actor.components.get("relationships"), intent.target_id, 5)
        target_relationships = _relationship_delta(target.components.get("relationships"), intent.actor_id, 8)
        correlation_id = intent.correlation_id or obligation_id
        return [
            NewEvent(
                tick=intent.tick,
                phase="resolution",
                event_type="social.repaid",
                actor_id=intent.actor_id,
                subject_ids=(intent.actor_id, intent.target_id),
                correlation_id=correlation_id,
                payload={
                    "obligation_id": obligation_id,
                    "target_id": intent.target_id,
                    "resource": resource,
                    "quantity": quantity,
                },
            ),
            NewEvent(
                tick=intent.tick,
                phase="social",
                event_type="obligation.fulfilled",
                actor_id=intent.actor_id,
                subject_ids=(intent.actor_id, intent.target_id),
                correlation_id=correlation_id,
                payload={
                    "obligation_id": obligation_id,
                    "debtor_id": intent.actor_id,
                    "creditor_id": intent.target_id,
                },
            ),
            NewEvent(
                tick=intent.tick,
                phase="effects",
                event_type="entity.component_set",
                actor_id=intent.actor_id,
                subject_ids=(intent.actor_id,),
                correlation_id=correlation_id,
                payload={"component": "inventory", "value": actor_inventory},
            ),
            NewEvent(
                tick=intent.tick,
                phase="effects",
                event_type="entity.component_set",
                actor_id=intent.actor_id,
                subject_ids=(intent.target_id,),
                correlation_id=correlation_id,
                payload={"component": "inventory", "value": target_inventory},
            ),
            NewEvent(
                tick=intent.tick,
                phase="effects",
                event_type="entity.component_set",
                actor_id=intent.actor_id,
                subject_ids=(intent.actor_id,),
                correlation_id=correlation_id,
                payload={"component": "relationships", "value": actor_relationships},
            ),
            NewEvent(
                tick=intent.tick,
                phase="effects",
                event_type="entity.component_set",
                actor_id=intent.actor_id,
                subject_ids=(intent.target_id,),
                correlation_id=correlation_id,
                payload={"component": "relationships", "value": target_relationships},
            ),
        ]


def _relationship_delta(raw: object, other_id: str, delta: int) -> dict[str, int]:
    values = dict(raw) if isinstance(raw, dict) else {}
    values[other_id] = max(-100, min(100, int(values.get(other_id, 0)) + delta))
    return {str(key): int(value) for key, value in values.items()}
