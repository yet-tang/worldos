from __future__ import annotations

from worldos_core.adaptive import AdaptiveMemoryModule
from worldos_core.events import NewEvent
from worldos_core.modules import ModuleContext
from worldos_core.store import InMemoryEventStore
from worldos_core.survival import SurvivalEconomyModule
from worldos_core.world import replay_world


def _bootstrap() -> InMemoryEventStore:
    store = InMemoryEventStore()
    store.append_batch(
        "main",
        [
            NewEvent(tick=0, phase="bootstrap", event_type="world.created", payload={"flags": {"seed": "phase-f-repeat-crisis"}}),
            NewEvent(
                tick=0,
                phase="bootstrap",
                event_type="entity.created",
                subject_ids=("buyer",),
                payload={
                    "kind": "character",
                    "components": {
                        "position": {"location_id": "market"},
                        "health": {"current": 100, "maximum": 100},
                        "needs": {"hunger": 78, "fatigue": 0},
                        "survival": {"hunger": 78, "fatigue": 0},
                        "metabolism": {"hunger_per_tick": 1, "fatigue_per_tick": 0},
                        "inventory": {"food": 0},
                        "wallet": 20,
                        "relationships": {"seller": 10},
                        "rumors": [],
                    },
                },
            ),
            NewEvent(
                tick=0,
                phase="bootstrap",
                event_type="entity.created",
                subject_ids=("seller",),
                payload={
                    "kind": "character",
                    "components": {
                        "position": {"location_id": "market"},
                        "health": {"current": 100, "maximum": 100},
                        "needs": {"hunger": 5, "fatigue": 0},
                        "survival": {"hunger": 5, "fatigue": 0},
                        "metabolism": {"hunger_per_tick": 0, "fatigue_per_tick": 0},
                        "inventory": {"food": 30},
                        "wallet": 0,
                        "relationships": {"buyer": 10},
                        "rumors": [],
                    },
                },
            ),
        ],
        expected_sequence=0,
    )
    return store


def _run_tick(store: InMemoryEventStore, tick: int) -> None:
    adaptive = AdaptiveMemoryModule()
    survival = SurvivalEconomyModule()

    history = tuple(store.read("main"))
    world = replay_world(list(history))
    adaptive_events = adaptive.before_actions(ModuleContext(timeline_id="main", tick=tick, world=world, history=history))
    if adaptive_events:
        store.append_batch("main", adaptive_events, expected_sequence=len(history))

    history = tuple(store.read("main"))
    world = replay_world(list(history))
    survival_events = survival.before_actions(ModuleContext(timeline_id="main", tick=tick, world=world, history=history))
    if survival_events:
        store.append_batch("main", survival_events, expected_sequence=len(history))


def _reset_physical_state(store: InMemoryEventStore, *, tick: int) -> None:
    history = store.read("main")
    store.append_batch(
        "main",
        [
            NewEvent(tick=tick, phase="test", event_type="entity.component_set", actor_id="buyer", subject_ids=("buyer",), payload={"component": "inventory", "value": {"food": 0}}),
            NewEvent(tick=tick, phase="test", event_type="entity.component_set", actor_id="buyer", subject_ids=("buyer",), payload={"component": "wallet", "value": 20}),
            NewEvent(tick=tick, phase="test", event_type="entity.component_set", actor_id="buyer", subject_ids=("buyer",), payload={"component": "needs", "value": {"hunger": 78, "fatigue": 0}}),
            NewEvent(tick=tick, phase="test", event_type="entity.component_set", actor_id="buyer", subject_ids=("buyer",), payload={"component": "survival", "value": {"hunger": 78, "fatigue": 0}}),
            NewEvent(tick=tick, phase="test", event_type="entity.component_set", actor_id="buyer", subject_ids=("buyer",), payload={"component": "rumors", "value": []}),
            NewEvent(tick=tick, phase="test", event_type="entity.component_set", actor_id="seller", subject_ids=("seller",), payload={"component": "inventory", "value": {"food": 30}}),
            NewEvent(tick=tick, phase="test", event_type="entity.component_set", actor_id="seller", subject_ids=("seller",), payload={"component": "wallet", "value": 0}),
        ],
        expected_sequence=len(history),
    )


def test_second_crisis_is_path_dependent_after_first_crisis_memory() -> None:
    experienced = _bootstrap()
    naive = _bootstrap()

    # First crisis exists only in the experienced history. It creates scarcity,
    # hoarding/rumor experiences and durable episodic memories on subsequent ticks.
    for tick in range(1, 9):
        _run_tick(experienced, tick)

    experienced_world = replay_world(experienced.read("main"))
    strategy = experienced_world.entities["buyer"].components.get("adaptive_strategy", {})
    assert strategy.get("experience_count", 0) > 0
    assert strategy.get("reserve_bonus", 0) > 0

    # Make physical conditions equal before the second crisis. The only intended
    # difference is history-derived memory/strategy carried by the experienced world.
    _reset_physical_state(experienced, tick=9)
    _reset_physical_state(naive, tick=9)

    # Naive world also receives the adaptive module once so default strategy/schema
    # exists, but it has no first-crisis memories to learn from.
    _run_tick(naive, 10)
    _run_tick(experienced, 10)

    experienced_state = replay_world(experienced.read("main")).entities["buyer"].components
    naive_state = replay_world(naive.read("main")).entities["buyer"].components
    exp_security = experienced_state["food_security"]
    naive_security = naive_state["food_security"]

    assert exp_security["adaptive_reserve_bonus"] > naive_security["adaptive_reserve_bonus"]
    assert exp_security["target_reserve"] > naive_security["target_reserve"]
    assert exp_security["pressure"] >= naive_security["pressure"]

    exp_evidence = [
        event for event in experienced.read("main")
        if event.tick == 10 and event.event_type == "decision.evidence" and event.actor_id == "buyer"
    ]
    assert any(event.payload.get("decision") == "update_adaptive_strategy" for event in exp_evidence)


def test_repeated_crisis_path_dependence_is_deterministic() -> None:
    def scenario() -> tuple[str, list[dict]]:
        store = _bootstrap()
        for tick in range(1, 9):
            _run_tick(store, tick)
        _reset_physical_state(store, tick=9)
        _run_tick(store, 10)
        world = replay_world(store.read("main"))
        normalized = [
            event.model_dump(exclude={"event_id", "sequence", "timeline_id"})
            for event in store.read("main")
        ]
        return world.canonical_hash(), normalized

    left_hash, left_events = scenario()
    right_hash, right_events = scenario()
    assert left_hash == right_hash
    assert left_events == right_events
