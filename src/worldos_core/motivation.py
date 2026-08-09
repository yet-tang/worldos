from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from .events import NewEvent
from .planning import Goal, PlannerProjection
from .social import SocialProjection
from .world import EntityProjection, WorldProjection


@dataclass(frozen=True)
class MotivationCandidate:
    owner_id: str
    motivation: str
    goal_type: str
    priority: int
    parameters: dict[str, Any]
    reason: str


class MotivationEngine:
    """Derive deterministic non-survival goals from character and social context."""

    cadence = 3
    cooldown = 6

    def derive(
        self,
        world: WorldProjection,
        planning: PlannerProjection,
        *,
        tick: int,
        social: SocialProjection | None = None,
    ) -> list[NewEvent]:
        events: list[NewEvent] = []
        actors = {
            entity_id: entity
            for entity_id, entity in sorted(world.entities.items())
            if entity.active and entity.kind == "character"
        }
        for owner_id, actor in actors.items():
            profile_key = f"{world.flags.get('seed', 'worldos')}:{owner_id}"
            personality = self._profile(actor.components.get("personality"), profile_key)
            drives = self._drives(actor.components.get("drives"), profile_key)
            if "personality" not in actor.components:
                events.append(
                    NewEvent(
                        tick=tick,
                        phase="cognition",
                        event_type="entity.component_set",
                        actor_id=owner_id,
                        subject_ids=(owner_id,),
                        payload={"component": "personality", "value": personality},
                    )
                )
            if "drives" not in actor.components:
                events.append(
                    NewEvent(
                        tick=tick,
                        phase="cognition",
                        event_type="entity.component_set",
                        actor_id=owner_id,
                        subject_ids=(owner_id,),
                        payload={"component": "drives", "value": drives},
                    )
                )

            if not self._due(profile_key, tick) or self._survival_is_urgent(actor):
                continue
            if any(goal.parameters.get("source_motivation") for goal in planning.active_goals(owner_id)):
                continue

            candidates = self._candidates(
                owner_id,
                actor,
                actors,
                personality,
                drives,
                profile_key,
                social,
                tick,
            )
            if not candidates:
                continue
            candidates.sort(
                key=lambda item: (
                    -item.priority,
                    item.goal_type,
                    json.dumps(item.parameters, ensure_ascii=False, sort_keys=True),
                )
            )
            for candidate in candidates[:4]:
                events.append(
                    NewEvent(
                        tick=tick,
                        phase="cognition",
                        event_type="motivation.considered",
                        actor_id=owner_id,
                        subject_ids=(owner_id,),
                        payload={
                            "motivation": candidate.motivation,
                            "goal_type": candidate.goal_type,
                            "priority": candidate.priority,
                            "parameters": candidate.parameters,
                            "reason": candidate.reason,
                        },
                    )
                )

            selected = candidates[0]
            if self._recently_pursued(planning, owner_id, selected.motivation, tick):
                continue
            goal = self._goal_for(selected, tick)
            events.extend(
                [
                    NewEvent(
                        tick=tick,
                        phase="cognition",
                        event_type="motivation.selected",
                        actor_id=owner_id,
                        subject_ids=(owner_id,),
                        correlation_id=goal.goal_id,
                        payload={
                            "motivation": selected.motivation,
                            "goal_type": selected.goal_type,
                            "priority": selected.priority,
                            "parameters": selected.parameters,
                            "reason": selected.reason,
                        },
                    ),
                    NewEvent(
                        tick=tick,
                        phase="cognition",
                        event_type="goal.created",
                        actor_id=owner_id,
                        subject_ids=(owner_id,),
                        correlation_id=goal.goal_id,
                        payload=goal.model_dump(mode="json"),
                    ),
                ]
            )
        return events

    def _candidates(
        self,
        owner_id: str,
        actor: EntityProjection,
        actors: dict[str, EntityProjection],
        personality: dict[str, int],
        drives: dict[str, int],
        profile_key: str,
        social: SocialProjection | None,
        tick: int,
    ) -> list[MotivationCandidate]:
        components = actor.components
        relationships = components.get("relationships", {})
        if not isinstance(relationships, dict):
            relationships = {}
        needs = components.get("needs", {})
        hunger = int(needs.get("hunger", 0)) if isinstance(needs, dict) else 0
        inventory = components.get("inventory", {})
        if not isinstance(inventory, dict):
            inventory = {}
        food = int(inventory.get("food", 0))

        candidates: list[MotivationCandidate] = []

        if social is not None:
            obligations = social.open_obligations_for_debtor(owner_id)
            if obligations:
                obligation = obligations[0]
                available = int(inventory.get(obligation.resource, 0))
                if available >= obligation.quantity and tick > obligation.created_tick:
                    bond = social.bond(owner_id, obligation.creditor_id)
                    remaining = obligation.due_tick - tick
                    deadline_pressure = max(0, 6 - remaining) * 4
                    priority = self._clamp(
                        42
                        + drives["status"] // 7
                        + drives["security"] // 9
                        + max(0, bond.trust) // 10
                        + deadline_pressure
                        - drives["wealth"] // 14,
                        1,
                        76,
                    )
                    candidates.append(
                        MotivationCandidate(
                            owner_id,
                            "reciprocity",
                            "repay_obligation",
                            priority,
                            {
                                "target_id": obligation.creditor_id,
                                "obligation_id": obligation.obligation_id,
                                "resource": obligation.resource,
                                "quantity": obligation.quantity,
                                "due_tick": obligation.due_tick,
                            },
                            f"欠{obligation.creditor_id}一份{obligation.resource}人情，想在约定期限前兑现",
                        )
                    )

        if hunger >= 45 and food <= 1:
            target = self._best_resource_target(owner_id, actors, "food", minimum=3)
            if target is not None:
                relation = int(relationships.get(target, 0))
                priority = self._clamp(
                    48 + hunger // 3 + drives["security"] // 8 + max(-10, relation // 5),
                    1,
                    69,
                )
                candidates.append(
                    MotivationCandidate(
                        owner_id,
                        "security",
                        "request_resource",
                        priority,
                        {"target_id": target, "resource": "food", "quantity": 1},
                        "食物储备偏低，希望通过社会关系获得食物",
                    )
                )

        if personality["generosity"] >= 55 and food >= 3:
            target = self._hungriest_other(owner_id, actors, minimum_hunger=50)
            if target is not None:
                target_hunger = int(actors[target].components.get("needs", {}).get("hunger", 0))
                priority = self._clamp(
                    35 + personality["generosity"] // 3 + target_hunger // 5,
                    1,
                    67,
                )
                candidates.append(
                    MotivationCandidate(
                        owner_id,
                        "care",
                        "help_resident",
                        priority,
                        {"target_id": target, "resource": "food", "quantity": 1},
                        "注意到别人缺少食物，愿意主动帮助",
                    )
                )

        if drives["belonging"] >= 40 and personality["sociability"] >= 35:
            target = self._relationship_target(owner_id, actors, relationships, prefer_negative=False)
            if target is not None:
                relation = int(relationships.get(target, 0))
                priority = self._clamp(
                    28 + drives["belonging"] // 3 + personality["sociability"] // 4 - max(0, relation // 3),
                    1,
                    62,
                )
                candidates.append(
                    MotivationCandidate(
                        owner_id,
                        "belonging",
                        "strengthen_relationship",
                        priority,
                        {"target_id": target},
                        "希望建立或改善一段社会关系",
                    )
                )

        if personality["assertiveness"] >= 58 and drives["status"] >= 45:
            target = self._relationship_target(owner_id, actors, relationships, prefer_negative=True)
            relation = int(relationships.get(target, 0)) if target else 0
            if target is not None and relation <= -8:
                priority = self._clamp(
                    30
                    + personality["assertiveness"] // 3
                    + drives["status"] // 4
                    + min(15, abs(relation) // 2),
                    1,
                    65,
                )
                candidates.append(
                    MotivationCandidate(
                        owner_id,
                        "status",
                        "confront_rival",
                        priority,
                        {"target_id": target},
                        "与对方存在负面关系，并希望维护地位或边界",
                    )
                )

        if drives["curiosity"] >= 58 and personality["risk_tolerance"] >= 38:
            destination = self._exploration_target(owner_id, actor, actors, profile_key)
            if destination is not None:
                priority = self._clamp(
                    24 + drives["curiosity"] // 3 + personality["risk_tolerance"] // 6,
                    1,
                    58,
                )
                candidates.append(
                    MotivationCandidate(
                        owner_id,
                        "curiosity",
                        "explore_location",
                        priority,
                        {"location_id": destination},
                        "对别处正在发生的事情感到好奇，想去看看",
                    )
                )
        return candidates

    def _due(self, profile_key: str, tick: int) -> bool:
        digest = hashlib.sha256(profile_key.encode("utf-8")).digest()
        return tick % self.cadence == digest[0] % self.cadence

    @staticmethod
    def _survival_is_urgent(actor: EntityProjection) -> bool:
        needs = actor.components.get("needs", {})
        if not isinstance(needs, dict):
            return False
        return int(needs.get("hunger", 0)) >= 70 or int(needs.get("fatigue", 0)) >= 75

    def _recently_pursued(
        self,
        planning: PlannerProjection,
        owner_id: str,
        motivation: str,
        tick: int,
    ) -> bool:
        if motivation == "reciprocity":
            return False
        return any(
            goal.parameters.get("source_motivation") == motivation
            and tick - goal.created_tick < self.cooldown
            for goal in planning.goals_by_owner.get(owner_id, {}).values()
        )

    @staticmethod
    def _stable_traits(profile_key: str, channel: str, names: tuple[str, ...]) -> dict[str, int]:
        digest = hashlib.sha256(f"{profile_key}:{channel}".encode("utf-8")).digest()
        return {
            name: 25 + digest[index % len(digest)] % 61
            for index, name in enumerate(names)
        }

    @staticmethod
    def _profile(raw: Any, profile_key: str) -> dict[str, int]:
        defaults = MotivationEngine._stable_traits(
            profile_key,
            "personality",
            ("sociability", "generosity", "assertiveness", "risk_tolerance"),
        )
        source = raw if isinstance(raw, dict) else {}
        return {
            key: MotivationEngine._clamp(source.get(key, value), 0, 100)
            for key, value in defaults.items()
        }

    @staticmethod
    def _drives(raw: Any, profile_key: str) -> dict[str, int]:
        defaults = MotivationEngine._stable_traits(
            profile_key,
            "drives",
            ("security", "belonging", "status", "wealth", "curiosity"),
        )
        source = raw if isinstance(raw, dict) else {}
        return {
            key: MotivationEngine._clamp(source.get(key, value), 0, 100)
            for key, value in defaults.items()
        }

    @staticmethod
    def _best_resource_target(
        owner_id: str,
        actors: dict[str, EntityProjection],
        resource: str,
        *,
        minimum: int,
    ) -> str | None:
        ranked: list[tuple[int, str]] = []
        for actor_id, actor in actors.items():
            if actor_id == owner_id:
                continue
            inventory = actor.components.get("inventory", {})
            amount = int(inventory.get(resource, 0)) if isinstance(inventory, dict) else 0
            if amount >= minimum:
                ranked.append((-amount, actor_id))
        ranked.sort()
        return ranked[0][1] if ranked else None

    @staticmethod
    def _hungriest_other(
        owner_id: str,
        actors: dict[str, EntityProjection],
        *,
        minimum_hunger: int,
    ) -> str | None:
        ranked: list[tuple[int, str]] = []
        for actor_id, actor in actors.items():
            if actor_id == owner_id:
                continue
            needs = actor.components.get("needs", {})
            hunger = int(needs.get("hunger", 0)) if isinstance(needs, dict) else 0
            if hunger >= minimum_hunger:
                ranked.append((-hunger, actor_id))
        ranked.sort()
        return ranked[0][1] if ranked else None

    @staticmethod
    def _relationship_target(
        owner_id: str,
        actors: dict[str, EntityProjection],
        relationships: dict[str, Any],
        *,
        prefer_negative: bool,
    ) -> str | None:
        ranked: list[tuple[int, str]] = []
        for actor_id in actors:
            if actor_id == owner_id:
                continue
            relation = int(relationships.get(actor_id, 0))
            score = relation if prefer_negative else abs(relation)
            ranked.append((score, actor_id))
        ranked.sort()
        return ranked[0][1] if ranked else None

    @staticmethod
    def _exploration_target(
        owner_id: str,
        actor: EntityProjection,
        actors: dict[str, EntityProjection],
        profile_key: str,
    ) -> str | None:
        current = actor.components.get("position", {}).get("location_id")
        locations = sorted(
            {
                other.components.get("position", {}).get("location_id")
                for actor_id, other in actors.items()
                if actor_id != owner_id and other.components.get("position", {}).get("location_id")
            }
            - {current}
        )
        if not locations:
            return None
        digest = hashlib.sha256(f"{profile_key}:explore".encode("utf-8")).digest()
        return locations[digest[0] % len(locations)]

    @staticmethod
    def _goal_for(candidate: MotivationCandidate, tick: int) -> Goal:
        parameters = dict(candidate.parameters)
        parameters["source_motivation"] = candidate.motivation
        parameters["reason"] = candidate.reason
        canonical = json.dumps(
            {
                "owner_id": candidate.owner_id,
                "motivation": candidate.motivation,
                "goal_type": candidate.goal_type,
                "priority": candidate.priority,
                "parameters": parameters,
                "tick": tick,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:20]
        return Goal(
            goal_id=f"goal_mot_{digest}",
            owner_id=candidate.owner_id,
            goal_type=candidate.goal_type,
            priority=candidate.priority,
            parameters=parameters,
            created_tick=tick,
        )

    @staticmethod
    def _clamp(value: Any, minimum: int, maximum: int) -> int:
        return max(minimum, min(maximum, int(value)))
