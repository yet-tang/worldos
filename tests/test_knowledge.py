from worldos_core import InMemoryEventStore, NewEvent, PerceptionEngine, replay_knowledge, replay_world


def _seed_world(store: InMemoryEventStore) -> None:
    store.append_batch("main", [
        NewEvent(tick=0, phase="world", event_type="entity.created", subject_ids=("alice",), payload={"kind": "person", "components": {"position": {"location_id": "inn"}}}),
        NewEvent(tick=0, phase="world", event_type="entity.created", subject_ids=("bob",), payload={"kind": "person", "components": {"position": {"location_id": "inn"}}}),
        NewEvent(tick=0, phase="world", event_type="entity.created", subject_ids=("carol",), payload={"kind": "person", "components": {"position": {"location_id": "road"}}}),
    ])


def test_colocated_observers_receive_observations_but_remote_entities_do_not() -> None:
    store = InMemoryEventStore()
    _seed_world(store)
    source = store.append_batch("main", [
        NewEvent(tick=1, phase="effects", event_type="health.changed", actor_id="alice", subject_ids=("bob",), payload={"delta": -5})
    ])
    derived = PerceptionEngine().process(store, "main", source, expected_sequence=4)
    knowledge = replay_knowledge(store.read("main"))

    assert derived
    assert "alice" in knowledge.beliefs_by_observer
    assert "bob" in knowledge.beliefs_by_observer
    assert "carol" not in knowledge.beliefs_by_observer


def test_world_projection_ignores_knowledge_events() -> None:
    store = InMemoryEventStore()
    _seed_world(store)
    before = replay_world(store.read("main")).canonical_hash()
    source = store.append_batch("main", [
        NewEvent(tick=1, phase="effects", event_type="health.changed", actor_id="alice", subject_ids=("bob",), payload={"delta": -5})
    ])
    PerceptionEngine().process(store, "main", source, expected_sequence=4)
    after = replay_world(store.read("main"))

    assert after.entities["bob"].components["health"]["current"] == 95
    assert before != after.canonical_hash()


def test_perception_is_deterministic() -> None:
    store = InMemoryEventStore()
    _seed_world(store)
    source = store.append_batch("main", [
        NewEvent(tick=1, phase="effects", event_type="entity.moved", actor_id="alice", subject_ids=("alice",), payload={"to_location_id": "road"})
    ])
    state = replay_world(store.read("main"))
    engine = PerceptionEngine()

    first = [event.model_dump(mode="json") for event in engine.derive(source, state)]
    second = [event.model_dump(mode="json") for event in engine.derive(source, state)]
    assert first == second
