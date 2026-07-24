import pytest

from worldos_core.events import NewEvent
from worldos_core.memory import replay_memory
from worldos_core.scheduler import DeterministicTickEngine, TickAlreadyCompletedError
from worldos_core.store import InMemoryEventStore
from worldos_core.world import replay_world


def _seed(store: InMemoryEventStore) -> None:
    store.append_batch("main", [
        NewEvent(tick=0, phase="projection", event_type="entity.created", subject_ids=("hero",), payload={"kind":"character","components":{"position":{"location_id":"road"}}}),
        NewEvent(tick=0, phase="projection", event_type="entity.created", subject_ids=("witness",), payload={"kind":"character","components":{"position":{"location_id":"road"}}}),
        NewEvent(tick=0, phase="cognition", event_type="goal.created", actor_id="hero", subject_ids=("hero",), payload={"goal_id":"g1","owner_id":"hero","goal_type":"reach_location","priority":5,"parameters":{"location_id":"inn"},"created_tick":0}),
    ], expected_sequence=0)


def test_tick_runs_planning_action_perception_and_memory():
    store = InMemoryEventStore()
    _seed(store)
    result = DeterministicTickEngine(store, world_seed="seed").run_tick("main", 1)

    event_types = [event.event_type for event in result.committed_events]
    assert event_types[0] == "tick.started"
    assert "plan.step_created" in event_types
    assert "entity.moved" in event_types
    assert "observation.created" in event_types
    assert "belief.updated" in event_types
    assert "memory.recorded" in event_types
    assert event_types[-1] == "tick.completed"
    assert replay_world(store.read("main")).entities["hero"].components["position"]["location_id"] == "inn"
    assert replay_memory(store.read("main")).memories("hero")


def test_actor_order_is_stable():
    store = InMemoryEventStore()
    store.append_batch("main", [
        NewEvent(tick=0, phase="projection", event_type="entity.created", subject_ids=("b",), payload={"kind":"character","components":{"position":{"location_id":"road"}}}),
        NewEvent(tick=0, phase="projection", event_type="entity.created", subject_ids=("a",), payload={"kind":"character","components":{"position":{"location_id":"road"}}}),
        NewEvent(tick=0, phase="cognition", event_type="goal.created", actor_id="b", subject_ids=("b",), payload={"goal_id":"gb","owner_id":"b","goal_type":"reach_location","priority":1,"parameters":{"location_id":"inn"},"created_tick":0}),
        NewEvent(tick=0, phase="cognition", event_type="goal.created", actor_id="a", subject_ids=("a",), payload={"goal_id":"ga","owner_id":"a","goal_type":"reach_location","priority":1,"parameters":{"location_id":"inn"},"created_tick":0}),
    ], expected_sequence=0)
    result = DeterministicTickEngine(store, world_seed="seed").run_tick("main", 1)
    assert result.actors == ("a", "b")


def test_same_seed_and_history_produce_identical_events():
    first = InMemoryEventStore()
    second = InMemoryEventStore()
    _seed(first)
    _seed(second)
    left = DeterministicTickEngine(first, world_seed="seed").run_tick("main", 1)
    right = DeterministicTickEngine(second, world_seed="seed").run_tick("main", 1)
    assert [event.model_dump(mode="json") for event in left.committed_events] == [event.model_dump(mode="json") for event in right.committed_events]


def test_completed_tick_cannot_run_twice():
    store = InMemoryEventStore()
    _seed(store)
    engine = DeterministicTickEngine(store, world_seed="seed")
    engine.run_tick("main", 1)
    with pytest.raises(TickAlreadyCompletedError):
        engine.run_tick("main", 1)
