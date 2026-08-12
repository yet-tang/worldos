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
    """Turns salient lived events into durable episodic memory and adaptive strategy.

    The module never invents an outcome. It records what happened, summarizes repeated
    experience deterministically, and exposes strategy/social-structure components for
    domain modules to consume on subsequent ticks.
    """

    name = "adaptive_memory"
    order = 10

    def before_actions(self, context: ModuleContext) -> list[NewEvent]:
        if context.tick <= 0:
            return []
        events: list[NewEvent] = []
        existing_memory_ids = {
            str(event.payload.get("memory_id"))
            for event in context.history
            if event.event_type == "memory.recorded"
        }

        # Record only the immediately preceding tick. Completed timelines therefore do
        # not repeatedly rescan/re-emit their entire history after restart.
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
            strategy = self._strategy(actor_id, memories.get(actor_id, []))
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
                result[owner_id].append(content)
        return result

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
    def _strategy(cls, actor_id: str, memories: list[dict[str, Any]]) -> dict[str, Any]:
        counts: dict[str, int] = defaultdict(int)
        partner_score: dict[str, int] = defaultdict(int)
        for memory in memories:
            event_type = str(memory.get("experience_type"))
            counts[event_type] += 1
            other = cls._counterpart(actor_id, memory)
            if other:
                if event_type in {"trade.completed", "social.helped", "obligation.fulfilled"}:
                    partner_score[other] += 2
                elif event_type == "scarcity.purchase":
                    partner_score[other] += 1
                elif event_type in {"conflict.resolved", "obligation.defaulted"}:
                    partner_score[other] -= 3

        scarcity = counts["scarcity.perceived"]
        hoarding = counts["scarcity.purchase"]
        conflicts = counts["conflict.resolved"]
        rejected = counts["rumor.rejected"]
        accepted = counts["rumor.spread"]
        defaults = counts["obligation.defaulted"]
        fulfilled = counts["obligation.fulfilled"]

        preferred = [actor for actor, score in sorted(partner_score.items(), key=lambda item: (-item[1], item[0])) if score >= 2][:4]
        avoided = [actor for actor, score in sorted(partner_score.items(), key=lambda item: (item[1], item[0])) if score <= -2][:4]
        return {
            "reserve_bonus": min(6, scarcity // 5 + hoarding // 3),
            "rumor_skepticism": min(30, rejected * 2 + conflicts // 2),
            "conflict_caution": min(25, conflicts * 2),
            "reciprocity_bias": max(-20, min(20, fulfilled * 3 - defaults * 5)),
            "preferred_partners": preferred,
            "avoided_partners": avoided,
            "experience_count": len(memories),
            "evidence": {
                "scarcity_exposure": scarcity,
                "hoarding_experience": hoarding,
                "conflict_exposure": conflicts,
                "rumor_accepted": accepted,
                "rumor_rejected": rejected,
                "obligations_fulfilled": fulfilled,
                "obligations_defaulted": defaults,
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
