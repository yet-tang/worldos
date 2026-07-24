import json

from worldos_core.cli import build_demo_store, inspect, narrate, simulate
from worldos_core.inspector import WorldInspector


def _json_output(capsys):
    return json.loads(capsys.readouterr().out)


def test_demo_store_runs_full_runtime_chain():
    store = build_demo_store(ticks=1, world_seed="test-seed")
    events = store.read("main")
    event_types = [event.event_type for event in events]

    assert "tick.started" in event_types
    assert "plan.step_created" in event_types
    assert "entity.moved" in event_types
    assert "observation.created" in event_types
    assert "belief.updated" in event_types
    assert "memory.recorded" in event_types
    assert event_types[-1] == "tick.completed"
    assert WorldInspector(store).entity("traveler").components["position"]["location_id"] == "room_2"


def test_demo_store_is_deterministic():
    left = build_demo_store(ticks=1, world_seed="same")
    right = build_demo_store(ticks=1, world_seed="same")

    assert [event.model_dump(mode="json") for event in left.read("main")] == [
        event.model_dump(mode="json") for event in right.read("main")
    ]
    assert WorldInspector(left).snapshot().world_hash == WorldInspector(right).snapshot().world_hash


def test_simulate_command_emits_world_snapshot(capsys):
    simulate(1, "cli-seed")
    payload = _json_output(capsys)

    assert payload["timeline_id"] == "main"
    assert payload["ticks"] == 1
    assert payload["event_count"] > 4
    assert payload["world"]["entities"]["traveler"]["components"]["position"]["location_id"] == "room_2"


def test_inspect_command_emits_actor_debug_view(capsys):
    inspect("traveler", 1, "cli-seed")
    payload = _json_output(capsys)

    assert payload["actor_id"] == "traveler"
    assert payload["goals"]
    assert payload["plan_steps"]
    assert payload["memories"]


def test_narrate_command_preserves_actor_knowledge_boundary(capsys):
    narrate("witness", 1, "cli-seed")
    payload = _json_output(capsys)

    assert payload["mode"] == "actor"
    assert payload["perspective_actor_id"] == "witness"
    assert payload["world_hash"] is None
    assert payload["observations"]
