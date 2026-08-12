from __future__ import annotations

from worldos_core.adaptive import AdaptiveMemoryModule
from worldos_core.events import Event
from worldos_core.modules import ModuleContext
from worldos_core.world import EntityProjection, WorldProjection


def _event(*, event_id: str, tick: int, event_type: str, actor_id: str, subject_ids=(), payload=None) -> Event:
    return Event(
        event_id=event_id,
        timeline_id="main",
        sequence=1,
        tick=tick,
        phase="module",
        event_type=event_type,
        actor_id=actor_id,
        subject_ids=tuple(subject_ids),
        payload=payload or {},
    )


def test_salient_prior_tick_becomes_episodic_memory() -> None:
    source = _event(
        event_id="evt-conflict",
        tick=4,
        event_type="conflict.resolved",
        actor_id="a",
        subject_ids=("a", "b"),
        payload={"target_id": "b", "reason": "food_scarcity", "severity": 40},
    )
    world = WorldProjection(
        tick=4,
        entities={
            "a": EntityProjection(entity_id="a", kind="character", components={"relationships": {"b": -20}}),
            "b": EntityProjection(entity_id="b", kind="character", components={"relationships": {"a": -20}}),
        },
    )
    events = AdaptiveMemoryModule().before_actions(ModuleContext(timeline_id="main", tick=5, world=world, history=(source,)))
    memories = [event for event in events if event.event_type == "memory.recorded"]
    assert len(memories) == 2
    assert all(event.payload["kind"] == "episodic" for event in memories)
    assert all(event.payload["content"]["experience_type"] == "conflict.resolved" for event in memories)
    assert all(event.payload["salience"] == 1.0 for event in memories)


def test_repeated_experience_changes_strategy_and_social_structure() -> None:
    memories: list[Event] = []
    sequence = 1
    for index in range(6):
        memories.append(
            _event(
                event_id=f"mem-scarcity-{index}",
                tick=index + 1,
                event_type="memory.recorded",
                actor_id="a",
                payload={
                    "memory_id": f"m{index}",
                    "owner_id": "a",
                    "kind": "episodic",
                    "tick": index + 1,
                    "content": {"experience_type": "scarcity.perceived", "subject_ids": ["a"], "payload": {}},
                    "source_ids": (),
                    "confidence": 1.0,
                    "salience": 0.7,
                    "active": True,
                },
            ).model_copy(update={"sequence": sequence})
        )
        sequence += 1
    for index in range(3):
        memories.append(
            _event(
                event_id=f"mem-trade-{index}",
                tick=10 + index,
                event_type="memory.recorded",
                actor_id="a",
                payload={
                    "memory_id": f"trade{index}",
                    "owner_id": "a",
                    "kind": "episodic",
                    "tick": 10 + index,
                    "content": {"experience_type": "trade.completed", "subject_ids": ["a", "b"], "payload": {"seller_id": "b"}},
                    "source_ids": (),
                    "confidence": 1.0,
                    "salience": 0.8,
                    "active": True,
                },
            ).model_copy(update={"sequence": sequence})
        )
        sequence += 1
    memories.append(
        _event(
            event_id="mem-conflict",
            tick=15,
            event_type="memory.recorded",
            actor_id="a",
            payload={
                "memory_id": "conflict",
                "owner_id": "a",
                "kind": "episodic",
                "tick": 15,
                "content": {"experience_type": "conflict.resolved", "subject_ids": ["a", "c"], "payload": {"target_id": "c"}},
                "source_ids": (),
                "confidence": 1.0,
                "salience": 1.0,
                "active": True,
            },
        ).model_copy(update={"sequence": sequence})
    )
    world = WorldProjection(
        tick=16,
        entities={
            "a": EntityProjection(entity_id="a", kind="character", components={"relationships": {"b": 25, "c": -30}}),
            "b": EntityProjection(entity_id="b", kind="character", components={}),
            "c": EntityProjection(entity_id="c", kind="character", components={}),
        },
    )
    events = AdaptiveMemoryModule().before_actions(ModuleContext(timeline_id="main", tick=17, world=world, history=tuple(memories)))
    strategy_event = next(event for event in events if event.event_type == "entity.component_set" and event.actor_id == "a" and event.payload["component"] == "adaptive_strategy")
    strategy = strategy_event.payload["value"]
    assert strategy["reserve_bonus"] >= 1
    assert "b" in strategy["preferred_partners"]
    assert "c" in strategy["avoided_partners"]
    assert strategy["conflict_caution"] > 0
    structure_event = next(event for event in events if event.event_type == "entity.component_set" and event.actor_id == "a" and event.payload["component"] == "social_structure")
    assert "b" in structure_event.payload["value"]["trusted_circle"]
    assert "c" in structure_event.payload["value"]["avoidance_circle"]


def test_experience_memory_is_not_duplicated() -> None:
    source = _event(event_id="evt-trade", tick=3, event_type="trade.completed", actor_id="a", subject_ids=("a", "b"), payload={"seller_id": "b", "buyer_id": "a"})
    module = AdaptiveMemoryModule()
    memory_id = module._memory_id(source, "a")
    existing = _event(
        event_id="existing-memory-event",
        tick=4,
        event_type="memory.recorded",
        actor_id="a",
        payload={"memory_id": memory_id, "owner_id": "a", "kind": "episodic", "tick": 4, "content": {"experience_type": "trade.completed", "subject_ids": ["a", "b"], "payload": {}}, "source_ids": (), "confidence": 1.0, "salience": 0.8, "active": True},
    )
    world = WorldProjection(tick=3, entities={"a": EntityProjection(entity_id="a", kind="character", components={})})
    events = module.before_actions(ModuleContext(timeline_id="main", tick=4, world=world, history=(source, existing)))
    assert not [event for event in events if event.event_type == "memory.recorded" and event.payload["memory_id"] == memory_id]
