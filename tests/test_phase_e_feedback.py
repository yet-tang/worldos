from worldos_core.events import NewEvent
from worldos_core.modules import ModuleContext
from worldos_core.store import InMemoryEventStore
from worldos_core.survival import SurvivalEconomyModule
from worldos_core.world import replay_world


def _tick(store: InMemoryEventStore, tick: int):
    history = tuple(store.read("main"))
    context = ModuleContext(timeline_id="main", tick=tick, world=replay_world(list(history)), history=history)
    return store.append_batch("main", SurvivalEconomyModule().before_actions(context), expected_sequence=len(history))


def test_scarcity_feedback_is_deterministic_across_identical_worlds():
    def seeded_store():
        store = InMemoryEventStore()
        store.append_batch("main", [
            NewEvent(tick=0, phase="bootstrap", event_type="world.created", payload={"flags": {"seed": "phase-e-seed"}}),
            NewEvent(tick=0, phase="bootstrap", event_type="entity.created", subject_ids=("a",), payload={"kind": "character", "components": {"position": {"location_id": "market"}, "health": {"current": 100, "maximum": 100}, "needs": {"hunger": 80, "fatigue": 0}, "survival": {"hunger": 80, "fatigue": 0}, "metabolism": {"hunger_per_tick": 1, "fatigue_per_tick": 0}, "inventory": {"food": 0}, "wallet": 8, "relationships": {"b": -10}, "rumors": ["粮食可能会短缺"]}}),
            NewEvent(tick=0, phase="bootstrap", event_type="entity.created", subject_ids=("b",), payload={"kind": "character", "components": {"position": {"location_id": "market"}, "health": {"current": 100, "maximum": 100}, "needs": {"hunger": 5, "fatigue": 0}, "survival": {"hunger": 5, "fatigue": 0}, "metabolism": {"hunger_per_tick": 1, "fatigue_per_tick": 0}, "inventory": {"food": 10}, "wallet": 0, "relationships": {"a": -10}, "rumors": []}}),
        ], expected_sequence=0)
        return store

    first, second = seeded_store(), seeded_store()
    for tick in range(1, 6):
        _tick(first, tick); _tick(second, tick)
    assert replay_world(first.read("main")).canonical_hash() == replay_world(second.read("main")).canonical_hash()
    left = [e.model_dump(exclude={"event_id", "sequence", "timeline_id"}) for e in first.read("main")]
    right = [e.model_dump(exclude={"event_id", "sequence", "timeline_id"}) for e in second.read("main")]
    assert left == right


def test_no_scarcity_does_not_force_conflict():
    store = InMemoryEventStore()
    store.append_batch("main", [
        NewEvent(tick=0, phase="bootstrap", event_type="world.created", payload={"flags": {"seed": "peaceful-seed"}}),
        NewEvent(tick=0, phase="bootstrap", event_type="entity.created", subject_ids=("a",), payload={"kind": "character", "components": {"position": {"location_id": "market"}, "health": {"current": 100, "maximum": 100}, "needs": {"hunger": 5, "fatigue": 0}, "survival": {"hunger": 5, "fatigue": 0}, "metabolism": {"hunger_per_tick": 0, "fatigue_per_tick": 0}, "inventory": {"food": 10}, "wallet": 10, "relationships": {"b": 20}, "rumors": []}}),
        NewEvent(tick=0, phase="bootstrap", event_type="entity.created", subject_ids=("b",), payload={"kind": "character", "components": {"position": {"location_id": "market"}, "health": {"current": 100, "maximum": 100}, "needs": {"hunger": 5, "fatigue": 0}, "survival": {"hunger": 5, "fatigue": 0}, "metabolism": {"hunger_per_tick": 0, "fatigue_per_tick": 0}, "inventory": {"food": 10}, "wallet": 10, "relationships": {"a": 20}, "rumors": []}}),
    ], expected_sequence=0)
    events = _tick(store, 1)
    assert not any(event.event_type == "conflict.resolved" for event in events)
    assert not any(event.event_type == "scarcity.purchase" for event in events)
