from __future__ import annotations

from collections import defaultdict
import hashlib
from typing import Any

from .events import Event, NewEvent
from .modules import BaseWorldModule, ModuleContext


EXPERIENCE_EVENT_TYPES = {
    "scarcity.perceived",
    "scarcity.purchase",
    "rumor.generated",
    "rumor.spread",
    "rumor.rejected",
    "trade.completed",
    "conflict.resolved",
    "social.helped",
    "obligation.fulfilled",
    "obligation.defaulted",
}


class AdaptiveMemoryModule(BaseWorldModule):
    """Turns lived events into durable memory whose influence changes over time.

    Memories remain immutable audit records. Strategy derives a deterministic effective
    strength from their age and repetition: isolated old experiences fade toward a
    non-zero floor, while repeated experience reinforces a pattern. This creates long-
    term adaptation without deleting history or introducing wall-clock dependence.
    """

    name = "adaptive_memory"
    order = 10
    decay_horizon_ticks = 200
    minimum_memory_strength = 0.2
    max_reinforcement = 0.5

    def before_actions(self, context: ModuleContext) -> list[NewEvent]:
        if context.tick <= 0:
            return []
        events: list[NewEvent] = []
        existing_memory_ids = {
            str(event.payload.get("memory_id"))
            for event in context.history
            if event.event_type == "memory.recorded"
        }

        for source in context.history:
            if source.tick != context.tick - 1 or source.event_type not in EXPERIENCE_EVENT_TYPES:
                continue
            for owner_id in self._owners(source):
                memory_id = self._memory_id(source, owner_id)
                if memory_id in existing_memory_ids:
                    continue
                existing_memory_ids.add(memory_id)
                events.append(
                    NewEvent(
                        tick=context.tick,
                        phase="memory",
                        event_type="memory.recorded",
                        actor_id=owner_id,
                        subject_ids=(owner_id,),
                        caused_by=(source.event_id,),
                        payload={
                            "memory_id": memory_id,
                            "owner_id": owner_id,
                            "kind": "episodic",
                            "tick": context.tick,
                            "content": {
                                "experience_type": source.event_type,
                                "source_tick": source.tick,
                                "actor_id": source.actor_id,
                                "subject_ids": list(source.subject_ids),
                                "payload": source.payload,
                            },
                            "source_ids": (source.event_id,),
                            "confidence": 1.0,
                            "salience": self._salience(source),
                            "active": True,
                        },
                    )
                )

        actors = {
            entity_id: entity
            for entity_id, entity in sorted(context.world.entities.items())
            if entity.active and entity.kind == "character"
        }
        memories = self._experience_memories(context.history)
        for actor_id, entity in actors.items():
            strategy = self._strategy(actor_id, memories.get(actor_id, []), current_tick=context.tick)
            if entity.components.get("adaptive_strategy") != strategy:
                events.append(
                    NewEvent(
                        tick=context.tick,
                        phase="adaptive",
                        event_type="entity.component_set",
                        actor_id=actor_id,
                        subject_ids=(actor_id,),
                        payload={"component": "adaptive_strategy", "value": strategy},
                    )
                )
                events.append(
                    NewEvent(
                        tick=context.tick,
                        phase="adaptive",
                        event_type="decision.evidence",
                        actor_id=actor_id,
                        subject_ids=(actor_id,),
                        payload={
                            "decision": "update_adaptive_strategy",
                            "because": strategy["evidence"],
                            "strategy": {key: value for key, value in strategy.items() if key != "evidence"},
                        },
                    )
                )

            structure = self._social_structure(actor_id, entity.components, strategy)
            if entity.components.get("social_structure") != structure:
                events.append(
                    NewEvent(
                        tick=context.tick,
                        phase="adaptive",
                        event_type="entity.component_set",
                        actor_id=actor_id,
                        subject_ids=(actor_id,),
                        payload={"component": "social_structure", "value": structure},
                    )
                )
        return events

    @staticmethod
    def _owners(event: Event) -> tuple[str, ...]:
        owners: list[str] = []
        if event.actor_id:
            owners.append(event.actor_id)
        for subject_id in event.subject_ids:
            if subject_id and subject_id not in owners:
                owners.append(subject_id)
        return tuple(owners)

    @staticmethod
    def _memory_id(source: Event, owner_id: str) -> str:
        digest = hashlib.sha256(f"{source.event_id}:{owner_id}:experience".encode("utf-8")).hexdigest()[:24]
        return f"mem_experience_{digest}"

    @staticmethod
    def _salience(event: Event) -> float:
        if event.event_type == "conflict.resolved":
            return 1.0
        if event.event_type in {"obligation.defaulted", "scarcity.purchase"}:
            return 0.9
        if event.event_type in {"social.helped", "obligation.fulfilled", "trade.completed"}:
            return 0.8
        return 0.7

    @staticmethod
    def _experience_memories(history: tuple[Event, ...]) -> dict[str, list[dict[str, Any]]]:
        result: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for event in history:
            if event.event_type != "memory.recorded" or event.payload.get("kind") != "episodic":
                continue
            content = event.payload.get("content", {})
            if not isinstance(content, dict) or content.get("experience_type") not in EXPERIENCE_EVENT_TYPES:
                continue
            owner_id = str(event.payload.get("owner_id") or "")
            if owner_id:
                result[owner_id].append(
                    {
                        "content": content,
                        "recorded_tick": int(event.payload.get("tick", event.tick)),
                        "salience": float(event.payload.get("salience", 0.7)),
                        "confidence": float(event.payload.get("confidence", 1.0)),
                    }
                )
        return result

    @classmethod
    def _memory_strength(cls, memory: dict[str, Any], *, current_tick: int, repetition_count: int) -> float:
        age = max(0, current_tick - int(memory.get("recorded_tick", current_tick)))
        decay = max(cls.minimum_memory_strength, 1.0 - age / cls.decay_horizon_ticks)
        reinforcement = 1.0 + min(cls.max_reinforcement, max(0, repetition_count - 1) * 0.05)
        salience = max(0.1, min(1.0, float(memory.get("salience", 0.7))))
        confidence = max(0.0, min(1.0, float(memory.get("confidence", 1.0))))
        salience_factor = 0.75 + 0.25 * salience
        return round(decay * reinforcement * salience_factor * confidence, 4)

    @staticmethod
    def _counterpart(owner_id: str, experience: dict[str, Any]) -> str | None:
        subject_ids = [str(item) for item in experience.get("subject_ids", [])]
        for subject_id in subject_ids:
            if subject_id != owner_id:
                return subject_id
        payload = experience.get("payload", {})
        if isinstance(payload, dict):
            for key in ("seller_id", "buyer_id", "target_id", "source_id", "creditor_id", "debtor_id"):
                value = str(payload.get(key) or "")
                if value and value != owner_id:
                    return value
        return None

    @classmethod
    def _strategy(cls, actor_id: str, memories: list[dict[str, Any]], *, current_tick: int = 0) -> dict[str, Any]:
        raw_counts: dict[str, int] = defaultdict(int)
        for memory in memories:
            content = memory.get("content", memory)
            raw_counts[str(content.get("experience_type"))] += 1

        weighted: dict[str, float] = defaultdict(float)
        partner_score: dict[str, float] = defaultdict(float)
        for memory in memories:
            content = memory.get("content", memory)
            event_type = str(content.get("experience_type"))
            strength = cls._memory_strength(memory, current_tick=current_tick, repetition_count=raw_counts[event_type])
            weighted[event_type] += strength
            other = cls._counterpart(actor_id, content)
            if other:
                if event_type in {"trade.completed", "social.helped", "obligation.fulfilled"}:
                    partner_score[other] += 2 * strength
                elif event_type == "scarcity.purchase":
                    partner_score[other] += strength
                elif event_type in {"conflict.resolved", "obligation.defaulted"}:
                    partner_score[other] -= 3 * strength

        scarcity = weighted["scarcity.perceived"]
        hoarding = weighted["scarcity.purchase"]
        conflicts = weighted["conflict.resolved"]
        rejected = weighted["rumor.rejected"]
        accepted = weighted["rumor.spread"]
        defaults = weighted["obligation.defaulted"]
        fulfilled = weighted["obligation.fulfilled"]

        preferred = [actor for actor, score in sorted(partner_score.items(), key=lambda item: (-item[1], item[0])) if score >= 1.5][:4]
        avoided = [actor for actor, score in sorted(partner_score.items(), key=lambda item: (item[1], item[0])) if score <= -1.5][:4]
        return {
            "reserve_bonus": min(6, int(scarcity // 5 + hoarding // 3)),
            "rumor_skepticism": min(30, int(rejected * 2 + conflicts / 2)),
            "conflict_caution": min(25, int(conflicts * 2)),
            "reciprocity_bias": max(-20, min(20, int(round(fulfilled * 3 - defaults * 5)))),
            "preferred_partners": preferred,
            "avoided_partners": avoided,
            "experience_count": len(memories),
            "evidence": {
                "scarcity_exposure": raw_counts["scarcity.perceived"],
                "hoarding_experience": raw_counts["scarcity.purchase"],
                "conflict_exposure": raw_counts["conflict.resolved"],
                "rumor_accepted": raw_counts["rumor.spread"],
                "rumor_rejected": raw_counts["rumor.rejected"],
                "obligations_fulfilled": raw_counts["obligation.fulfilled"],
                "obligations_defaulted": raw_counts["obligation.defaulted"],
                "effective_scarcity_exposure": round(scarcity, 3),
                "effective_conflict_exposure": round(conflicts, 3),
                "memory_decay_horizon": cls.decay_horizon_ticks,
            },
        }

    @staticmethod
    def _social_structure(actor_id: str, components: dict[str, Any], strategy: dict[str, Any]) -> dict[str, Any]:
        raw = components.get("relationships", {})
        relationships = raw if isinstance(raw, dict) else {}
        trusted = [other for other, value in sorted(relationships.items(), key=lambda item: (-int(item[1]), item[0])) if other != actor_id and int(value) >= 15][:5]
        hostile = [other for other, value in sorted(relationships.items(), key=lambda item: (int(item[1]), item[0])) if other != actor_id and int(value) <= -15][:5]
        for other in strategy.get("preferred_partners", []):
            if other not in trusted:
                trusted.append(other)
        for other in strategy.get("avoided_partners", []):
            if other not in hostile:
                hostile.append(other)
        return {
            "trusted_circle": trusted[:5],
            "avoidance_circle": hostile[:5],
            "network_stability": max(0, 100 - len(hostile) * 12 + len(trusted) * 5),
        }
