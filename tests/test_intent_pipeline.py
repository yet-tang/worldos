import pytest

from worldos_core.events import NewEvent
from worldos_core.intents import Intent
from worldos_core.pipeline import IntentPipeline
from worldos_core.store import EventStoreError, InMemoryEventStore
from worldos_core.world import replay_world


def bootstrap_store() -> InMemoryEventStore:
    store = InMemoryEventStore()
    store.append_batch(
        "main",
        [
            NewEvent(tick=0, phase="bootstrap", event_type="world.created", payload={"flags": {"seed": "inn"}}),
            NewEvent(tick=0, phase="bootstrap", event_type="entity.created", subject_ids=("assassin",), payload={"kind": "human", "components": {"position": {"location_id": "hall"}, "health": {"current": 100, "maximum": 100}, "combat": {"skill": 70, "defense": 10}}}),
            NewEvent(tick=0, phase="bootstrap", event_type="entity.created", subject_ids=("merchant",), payload={"kind": "human", "components": {"position": {"location_id": "hall"}, "health": {"current": 100, "maximum": 100}, "combat": {"skill": 20, "defense": 20}}}),
        ],
    )
    return store


def test_move_intent_resolves_to_atomic_event_batch():
    store = bootstrap_store()
    pipeline = IntentPipeline(store, world_seed="snowbound-inn")
    result = pipeline.process("main", Intent(tick=1, intent_type="move", actor_id="merchant", parameters={"to_location_id": "room-2"}), expected_sequence=3)
    assert result.accepted is True
    assert [event.event_type for event in result.committed_events] == ["move.attempted", "move.resolved", "entity.moved"]
    assert replay_world(store.read("main")).entities["merchant"].components["position"]["location_id"] == "room-2"


def test_invalid_attack_is_recorded_without_world_effect():
    store = bootstrap_store()
    pipeline = IntentPipeline(store, world_seed="snowbound-inn")
    pipeline.process("main", Intent(tick=1, intent_type="move", actor_id="merchant", parameters={"to_location_id": "room-2"}), expected_sequence=3)
    before = replay_world(store.read("main"))
    result = pipeline.process("main", Intent(tick=2, intent_type="attack", actor_id="assassin", target_id="merchant", parameters={"damage": 30}), expected_sequence=6)
    assert result.accepted is False
    assert result.issues[0].code == "out_of_range"
    assert [event.event_type for event in result.committed_events] == ["intent.rejected"]
    after = replay_world(store.read("main"))
    assert after.entities["merchant"].components["health"] == before.entities["merchant"].components["health"]


def test_attack_resolution_is_deterministic_and_replayable():
    def run_once():
        store = bootstrap_store()
        pipeline = IntentPipeline(store, world_seed="snowbound-inn")
        result = pipeline.process("main", Intent(tick=1, intent_type="attack", actor_id="assassin", target_id="merchant", parameters={"damage": 30}), expected_sequence=3)
        return result, replay_world(store.read("main"))

    first_result, first_state = run_once()
    second_result, second_state = run_once()
    assert [event.model_dump() for event in first_result.committed_events] == [event.model_dump() for event in second_result.committed_events]
    assert first_state == second_state
    assert first_state.canonical_hash() == second_state.canonical_hash()


def test_concurrency_conflict_prevents_partial_event_batch():
    store = bootstrap_store()
    pipeline = IntentPipeline(store, world_seed="snowbound-inn")
    with pytest.raises(EventStoreError):
        pipeline.process("main", Intent(tick=1, intent_type="move", actor_id="merchant", parameters={"to_location_id": "room-2"}), expected_sequence=2)
    assert len(store.read("main")) == 3


def test_unsupported_intent_is_auditable_rejection():
    store = bootstrap_store()
    pipeline = IntentPipeline(store, world_seed="snowbound-inn")
    result = pipeline.process("main", Intent(tick=1, intent_type="teleport", actor_id="merchant", parameters={"to_location_id": "roof"}), expected_sequence=3)
    assert result.accepted is False
    assert result.issues[0].code == "unsupported_intent"
    assert store.read("main")[-1].event_type == "intent.rejected"
