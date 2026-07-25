from __future__ import annotations

from copy import deepcopy
from typing import Any

from .events import NewEvent
from .modules import BaseWorldModule, ModuleContext


class SurvivalEconomyModule(BaseWorldModule):
    """Deterministic metabolism, production, trade, rumor, and conflict runtime."""

    name = "survival_economy"
    order = 20

    def before_actions(self, context: ModuleContext) -> list[NewEvent]:
        actors = {
            entity_id: entity
            for entity_id, entity in sorted(context.world.entities.items())
            if entity.active and entity.kind == "character"
        }
        staged = {entity_id: deepcopy(entity.components) for entity_id, entity in actors.items()}
        audit: list[NewEvent] = []
        health_events: list[NewEvent] = []

        for actor_id in sorted(staged):
            components = staged[actor_id]
            survival = dict(components.get("survival", {}))
            needs = dict(components.get("needs", {}))
            metabolism = dict(components.get("metabolism", {}))
            hunger = self._clamp(needs.get("hunger", survival.get("hunger", 0)) + metabolism.get("hunger_per_tick", 1), 0, 100)
            fatigue = self._clamp(needs.get("fatigue", survival.get("fatigue", 0)) + metabolism.get("fatigue_per_tick", 1), 0, 100)
            needs.update({"hunger": hunger, "fatigue": fatigue})
            survival.update({"hunger": hunger, "fatigue": fatigue})
            components["needs"] = needs
            components["survival"] = survival
            audit.append(self._audit(context.tick, "survival.metabolized", actor_id, {"hunger": hunger, "fatigue": fatigue}))
            if hunger >= 100:
                health_events.append(NewEvent(tick=context.tick, phase="module", event_type="health.changed", actor_id=actor_id, subject_ids=(actor_id,), payload={"delta": -1, "reason": "starvation"}))
            if fatigue >= 100:
                health_events.append(NewEvent(tick=context.tick, phase="module", event_type="health.changed", actor_id=actor_id, subject_ids=(actor_id,), payload={"delta": -1, "reason": "exhaustion"}))

            job = components.get("job")
            if isinstance(job, dict) and job.get("resource") and int(job.get("rate", 0)) > 0:
                resource = str(job["resource"])
                quantity = int(job["rate"])
                inventory = dict(components.get("inventory", {}))
                inventory[resource] = int(inventory.get(resource, 0)) + quantity
                components["inventory"] = inventory
                audit.append(self._audit(context.tick, "resource.produced", actor_id, {"resource": resource, "quantity": quantity}))

        self._process_trades(context, staged, audit)
        self._spread_rumors(context, staged, audit)
        self._resolve_conflicts(context, staged, audit, health_events)

        changes: list[NewEvent] = []
        for actor_id in sorted(staged):
            original = actors[actor_id].components
            current = staged[actor_id]
            for component in sorted(set(original) - set(current)):
                changes.append(NewEvent(tick=context.tick, phase="module", event_type="entity.component_removed", actor_id=actor_id, subject_ids=(actor_id,), payload={"component": component}))
            for component, value in sorted(current.items()):
                if original.get(component) != value:
                    changes.append(NewEvent(tick=context.tick, phase="module", event_type="entity.component_set", actor_id=actor_id, subject_ids=(actor_id,), payload={"component": component, "value": value}))
        return changes + health_events + audit

    def _process_trades(self, context: ModuleContext, staged: dict[str, dict[str, Any]], audit: list[NewEvent]) -> None:
        for seller_id in sorted(staged):
            offer = staged[seller_id].get("trade_offer")
            if not isinstance(offer, dict):
                continue
            buyer_id = str(offer.get("buyer_id", ""))
            if buyer_id not in staged or not self._same_location(staged[seller_id], staged[buyer_id]):
                continue
            resource = str(offer.get("resource", ""))
            quantity = max(0, int(offer.get("quantity", 0)))
            price = max(0, int(offer.get("price", 0)))
            seller_inventory = dict(staged[seller_id].get("inventory", {}))
            buyer_inventory = dict(staged[buyer_id].get("inventory", {}))
            seller_wallet = int(staged[seller_id].get("wallet", 0))
            buyer_wallet = int(staged[buyer_id].get("wallet", 0))
            if not resource or quantity <= 0 or int(seller_inventory.get(resource, 0)) < quantity or buyer_wallet < price:
                continue
            seller_inventory[resource] = int(seller_inventory.get(resource, 0)) - quantity
            buyer_inventory[resource] = int(buyer_inventory.get(resource, 0)) + quantity
            staged[seller_id]["inventory"] = seller_inventory
            staged[buyer_id]["inventory"] = buyer_inventory
            staged[seller_id]["wallet"] = seller_wallet + price
            staged[buyer_id]["wallet"] = buyer_wallet - price
            staged[seller_id].pop("trade_offer", None)
            self._change_relationship(staged[seller_id], buyer_id, 2)
            self._change_relationship(staged[buyer_id], seller_id, 2)
            audit.append(NewEvent(tick=context.tick, phase="module", event_type="trade.completed", actor_id=buyer_id, subject_ids=(seller_id, buyer_id), payload={"seller_id": seller_id, "buyer_id": buyer_id, "resource": resource, "quantity": quantity, "price": price}))

    def _spread_rumors(self, context: ModuleContext, staged: dict[str, dict[str, Any]], audit: list[NewEvent]) -> None:
        actor_ids = sorted(staged)
        for source_id in actor_ids:
            source_rumors = sorted({str(item) for item in staged[source_id].get("rumors", [])})
            if not source_rumors:
                continue
            for target_id in actor_ids:
                if target_id == source_id or not self._same_location(staged[source_id], staged[target_id]):
                    continue
                target_rumors = {str(item) for item in staged[target_id].get("rumors", [])}
                missing = [rumor for rumor in source_rumors if rumor not in target_rumors]
                if not missing:
                    continue
                rumor = missing[0]
                staged[target_id]["rumors"] = sorted(target_rumors | {rumor})
                audit.append(NewEvent(tick=context.tick, phase="module", event_type="rumor.spread", actor_id=source_id, subject_ids=(source_id, target_id), payload={"source_id": source_id, "target_id": target_id, "rumor": rumor}))

    def _resolve_conflicts(self, context: ModuleContext, staged: dict[str, dict[str, Any]], audit: list[NewEvent], health_events: list[NewEvent]) -> None:
        for aggressor_id in sorted(staged):
            conflict = staged[aggressor_id].get("conflict")
            if not isinstance(conflict, dict):
                continue
            target_id = str(conflict.get("target_id", ""))
            severity = self._clamp(conflict.get("severity", 1), 1, 100)
            if target_id not in staged or target_id == aggressor_id or not self._same_location(staged[aggressor_id], staged[target_id]):
                continue
            damage = max(1, severity // 20)
            health_events.append(NewEvent(tick=context.tick, phase="module", event_type="health.changed", actor_id=aggressor_id, subject_ids=(target_id,), payload={"delta": -damage, "reason": "conflict", "aggressor_id": aggressor_id}))
            self._change_relationship(staged[aggressor_id], target_id, -severity)
            self._change_relationship(staged[target_id], aggressor_id, -severity)
            staged[aggressor_id].pop("conflict", None)
            audit.append(NewEvent(tick=context.tick, phase="module", event_type="conflict.resolved", actor_id=aggressor_id, subject_ids=(aggressor_id, target_id), payload={"aggressor_id": aggressor_id, "target_id": target_id, "severity": severity, "damage": damage}))

    @staticmethod
    def _same_location(left: dict[str, Any], right: dict[str, Any]) -> bool:
        return left.get("position", {}).get("location_id") == right.get("position", {}).get("location_id")

    @staticmethod
    def _change_relationship(components: dict[str, Any], other_id: str, delta: int) -> None:
        relationships = dict(components.get("relationships", {}))
        relationships[other_id] = SurvivalEconomyModule._clamp(relationships.get(other_id, 0) + delta, -100, 100)
        components["relationships"] = relationships

    @staticmethod
    def _clamp(value: Any, minimum: int, maximum: int) -> int:
        return max(minimum, min(maximum, int(value)))

    @staticmethod
    def _audit(tick: int, event_type: str, actor_id: str, payload: dict[str, Any]) -> NewEvent:
        return NewEvent(tick=tick, phase="module", event_type=event_type, actor_id=actor_id, subject_ids=(actor_id,), payload=payload)
