from __future__ import annotations

from worldos_core.modules import ModuleContext
from worldos_core.survival import SurvivalEconomyModule
from worldos_core.world import EntityProjection, WorldProjection


def test_prior_scarcity_memory_increases_future_food_reserve_target() -> None:
    actor = EntityProjection(
        entity_id="a",
        kind="character",
        components={
            "position": {"location_id": "market"},
            "health": {"current": 100, "maximum": 100},
            "needs": {"hunger": 25, "fatigue": 0},
            "survival": {"hunger": 25, "fatigue": 0},
            "metabolism": {"hunger_per_tick": 0, "fatigue_per_tick": 0},
            "inventory": {"food": 4},
            "wallet": 10,
            "rumors": [],
            "adaptive_strategy": {
                "reserve_bonus": 4,
                "rumor_skepticism": 0,
                "conflict_caution": 0,
                "preferred_partners": [],
                "avoided_partners": [],
            },
        },
    )
    world = WorldProjection(tick=10, flags={"seed": "adaptive-test"}, entities={"a": actor})
    events = SurvivalEconomyModule().before_actions(ModuleContext(timeline_id="main", tick=11, world=world, history=()))
    food_security = next(
        event.payload["value"]
        for event in events
        if event.event_type == "entity.component_set" and event.actor_id == "a" and event.payload["component"] == "food_security"
    )
    assert food_security["adaptive_reserve_bonus"] == 4
    assert food_security["target_reserve"] >= 7
    assert food_security["shortage"] > 0


def test_rumor_skepticism_raises_acceptance_threshold() -> None:
    source = EntityProjection(
        entity_id="source",
        kind="character",
        components={
            "position": {"location_id": "market"},
            "health": {"current": 100, "maximum": 100},
            "needs": {"hunger": 0, "fatigue": 0},
            "survival": {"hunger": 0, "fatigue": 0},
            "metabolism": {"hunger_per_tick": 0, "fatigue_per_tick": 0},
            "inventory": {"food": 10},
            "wallet": 0,
            "relationships": {"target": 0},
            "rumors": ["粮食可能会短缺"],
        },
    )
    target = EntityProjection(
        entity_id="target",
        kind="character",
        components={
            "position": {"location_id": "market"},
            "health": {"current": 100, "maximum": 100},
            "needs": {"hunger": 0, "fatigue": 0},
            "survival": {"hunger": 0, "fatigue": 0},
            "metabolism": {"hunger_per_tick": 0, "fatigue_per_tick": 0},
            "inventory": {"food": 10},
            "wallet": 0,
            "relationships": {"source": 0},
            "rumors": [],
            "adaptive_strategy": {
                "reserve_bonus": 0,
                "rumor_skepticism": 30,
                "conflict_caution": 0,
                "preferred_partners": [],
                "avoided_partners": [],
            },
        },
    )
    world = WorldProjection(tick=10, flags={"seed": "adaptive-rumor"}, entities={"source": source, "target": target})
    events = SurvivalEconomyModule().before_actions(ModuleContext(timeline_id="main", tick=11, world=world, history=()))
    rumor_events = [event for event in events if event.event_type in {"rumor.spread", "rumor.rejected"} and "target" in event.subject_ids]
    assert rumor_events
    assert all(event.payload.get("adaptive_skepticism") == 30 for event in rumor_events)


def test_conflict_caution_can_prevent_marginal_scarcity_conflict() -> None:
    hungry = EntityProjection(
        entity_id="hungry",
        kind="character",
        components={
            "position": {"location_id": "market"},
            "health": {"current": 100, "maximum": 100},
            "needs": {"hunger": 100, "fatigue": 0},
            "survival": {"hunger": 100, "fatigue": 0},
            "metabolism": {"hunger_per_tick": 0, "fatigue_per_tick": 0},
            "inventory": {"food": 0},
            "wallet": 0,
            "relationships": {"holder": -20},
            "rumors": ["粮食可能会短缺", "有人囤粮", "市场已经断粮"],
            "food_security": {"food": 0, "target_reserve": 8, "shortage": 8, "pressure": 100, "rumor_pressure": 3, "scarcity_ticks": 5},
            "adaptive_strategy": {
                "reserve_bonus": 0,
                "rumor_skepticism": 0,
                "conflict_caution": 25,
                "preferred_partners": [],
                "avoided_partners": [],
            },
        },
    )
    holder = EntityProjection(
        entity_id="holder",
        kind="character",
        components={
            "position": {"location_id": "market"},
            "health": {"current": 100, "maximum": 100},
            "needs": {"hunger": 0, "fatigue": 0},
            "survival": {"hunger": 0, "fatigue": 0},
            "metabolism": {"hunger_per_tick": 0, "fatigue_per_tick": 0},
            "inventory": {"food": 8},
            "wallet": 0,
            "relationships": {"hungry": -20},
            "rumors": [],
        },
    )
    world = WorldProjection(tick=10, flags={"seed": "adaptive-conflict"}, entities={"hungry": hungry, "holder": holder})
    events = SurvivalEconomyModule().before_actions(ModuleContext(timeline_id="main", tick=11, world=world, history=()))
    assert not [event for event in events if event.event_type == "conflict.resolved" and event.actor_id == "hungry"]
