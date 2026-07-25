from worldos_core.events import NewEvent
from worldos_core.modules import ModuleContext
from worldos_core.store import InMemoryEventStore
from worldos_core.survival import SurvivalEconomyModule
from worldos_core.world import replay_world


def _seed(store: InMemoryEventStore) -> None:
    store.append_batch(
        "main",
        [
            NewEvent(
                tick=0,
                phase="projection",
                event_type="entity.created",
                subject_ids=("alice",),
                payload={
                    "kind": "character",
                    "components": {
                        "position": {"location_id": "market"},
                        "health": {"current": 100, "maximum": 100},
                        "needs": {"hunger": 99, "fatigue": 10},
                        "metabolism": {"hunger_per_tick": 1, "fatigue_per_tick": 2},
                        "job": {"resource": "food", "rate": 3},
                        "inventory": {"food": 1},
                        "wallet": 0,
                        "trade_offer": {"buyer_id": "bob", "resource": "food", "quantity": 2, "price": 4},
                        "rumors": ["the well is dry"],
                        "relationships": {},
                        "conflict": {"target_id": "bob", "severity": 40},
                    },
                },
            ),
            NewEvent(
                tick=0,
                phase="projection",
                event_type="entity.created",
                subject_ids=("bob",),
                payload={
                    "kind": "character",
                    "components": {
                        "position": {"location_id": "market"},
                        "health": {"current": 100, "maximum": 100},
                        "needs": {"hunger": 10, "fatigue": 5},
                        "inventory": {},
                        "wallet": 10,
                        "rumors": [],
                        "relationships": {},
                    },
                },
            ),
        ],
        expected_sequence=0,
    )


def test_survival_economy_module_closes_deterministic_loop():
    store = InMemoryEventStore()
    _seed(store)
    history = tuple(store.read("main"))
    context = ModuleContext(timeline_id="main", tick=1, world=replay_world(list(history)), history=history)

    candidates = SurvivalEconomyModule().before_actions(context)
    committed = store.append_batch("main", candidates, expected_sequence=len(history))
    world = replay_world(store.read("main"))
    alice = world.entities["alice"].components
    bob = world.entities["bob"].components
    event_types = [event.event_type for event in committed]

    assert alice["needs"] == {"hunger": 100, "fatigue": 12}
    assert alice["inventory"]["food"] == 2
    assert bob["inventory"]["food"] == 2
    assert alice["wallet"] == 4
    assert bob["wallet"] == 6
    assert bob["health"]["current"] == 98
    assert bob["rumors"] == ["the well is dry"]
    assert alice["relationships"]["bob"] == -38
    assert bob["relationships"]["alice"] == -38
    assert "trade_offer" not in alice
    assert "conflict" not in alice
    assert event_types.count("health.changed") == 2
    assert {"survival.metabolized", "resource.produced", "trade.completed", "rumor.spread", "conflict.resolved"}.issubset(event_types)


def test_survival_economy_is_replay_deterministic():
    first = InMemoryEventStore()
    second = InMemoryEventStore()
    for store in (first, second):
        _seed(store)
        history = tuple(store.read("main"))
        context = ModuleContext(timeline_id="main", tick=1, world=replay_world(list(history)), history=history)
        store.append_batch("main", SurvivalEconomyModule().before_actions(context), expected_sequence=len(history))

    assert replay_world(first.read("main")).canonical_hash() == replay_world(second.read("main")).canonical_hash()
    assert [event.model_dump(exclude={"event_id", "timeline_id", "sequence"}) for event in first.read("main")] == [event.model_dump(exclude={"event_id", "timeline_id", "sequence"}) for event in second.read("main")]
