import pytest

from worldos_core.events import NewEvent
from worldos_core.store import EventStoreError, InMemoryEventStore
from worldos_core.world import replay_world


def history():
    return [
        NewEvent(tick=0, phase="bootstrap", event_type="world.created", payload={"flags": {"season": "winter"}}),
        NewEvent(
            tick=0,
            phase="bootstrap",
            event_type="entity.created",
            subject_ids=("alice",),
            payload={"kind": "human", "components": {"health": {"current": 100, "maximum": 100}}},
        ),
        NewEvent(tick=1, phase="resolution", event_type="health.changed", subject_ids=("alice",), payload={"delta": -30, "resolution_roll": 81}),
    ]


def test_replay_is_stable():
    store = InMemoryEventStore()
    store.append_batch("main", history(), expected_sequence=0)
    first = replay_world(store.read("main"))
    second = replay_world(store.read("main"))
    assert first == second
    assert first.canonical_hash() == second.canonical_hash()
    assert first.entities["alice"].components["health"]["current"] == 70


def test_branch_inherits_only_parent_prefix():
    store = InMemoryEventStore()
    store.append_batch("main", history(), expected_sequence=0)
    store.create_timeline("safe", parent_through_sequence=2)
    store.append_batch(
        "safe",
        [NewEvent(tick=1, phase="resolution", event_type="world.flag_set", payload={"name": "attack_avoided", "value": True})],
        expected_sequence=2,
    )
    main = replay_world(store.read("main"))
    safe = replay_world(store.read("safe"))
    assert main.entities["alice"].components["health"]["current"] == 70
    assert safe.entities["alice"].components["health"]["current"] == 100
    assert safe.flags["attack_avoided"] is True
    assert main.canonical_hash() != safe.canonical_hash()


def test_optimistic_concurrency_prevents_partial_history():
    store = InMemoryEventStore()
    store.append_batch("main", history()[:1], expected_sequence=0)
    with pytest.raises(EventStoreError):
        store.append_batch("main", history()[1:], expected_sequence=0)
    assert len(store.read("main")) == 1


def test_event_ids_are_deterministic_for_same_store_input():
    first = InMemoryEventStore()
    second = InMemoryEventStore()
    first_ids = [e.event_id for e in first.append_batch("main", history())]
    second_ids = [e.event_id for e in second.append_batch("main", history())]
    assert first_ids == second_ids
