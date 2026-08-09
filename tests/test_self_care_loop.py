from worldos_core.events import NewEvent
from worldos_core.scheduler import DeterministicTickEngine
from worldos_core.store import InMemoryEventStore
from worldos_core.survival import SurvivalEconomyModule
from worldos_core.world import replay_world


def _seed_critical_actor(store: InMemoryEventStore) -> None:
    store.append_batch(
        "main",
        [
            NewEvent(
                tick=0,
                phase="bootstrap",
                event_type="entity.created",
                subject_ids=("alice",),
                payload={
                    "kind": "character",
                    "components": {
                        "position": {"location_id": "farm"},
                        "health": {"current": 100, "maximum": 100},
                        "needs": {"hunger": 99, "fatigue": 99},
                        "survival": {"hunger": 99, "fatigue": 99},
                        "metabolism": {"hunger_per_tick": 1, "fatigue_per_tick": 1},
                        "inventory": {"food": 3},
                        "job": {"resource": "food", "rate": 1},
                    },
                },
            ),
            # Represents a world created before self-care policies existed. The new
            # NeedEngine must retire this stale hunger goal instead of letting it
            # block the new explicit eat behavior.
            NewEvent(
                tick=0,
                phase="cognition",
                event_type="goal.created",
                actor_id="alice",
                subject_ids=("alice",),
                correlation_id="legacy-hunger-goal",
                payload={
                    "goal_id": "legacy-hunger-goal",
                    "owner_id": "alice",
                    "goal_type": "survive",
                    "priority": 99,
                    "status": "active",
                    "parameters": {"source_need": "hunger"},
                    "created_tick": 0,
                },
            ),
        ],
        expected_sequence=0,
    )


def test_critical_actor_eats_rests_then_resumes_work():
    store = InMemoryEventStore()
    _seed_critical_actor(store)
    engine = DeterministicTickEngine(
        store,
        world_seed="self-care-seed",
        modules=(SurvivalEconomyModule(),),
    )

    first = engine.run_tick("main", 1)
    second = engine.run_tick("main", 2)
    third = engine.run_tick("main", 3)

    first_two_types = [
        event.event_type
        for result in (first, second)
        for event in result.committed_events
    ]
    all_types = [
        event.event_type
        for result in (first, second, third)
        for event in result.committed_events
    ]

    assert "eat.resolved" in first_two_types
    assert "rest.resolved" in first_two_types
    assert "goal.status_changed" in first_two_types
    assert "resource.produced" not in first_two_types
    assert "resource.produced" in [event.event_type for event in third.committed_events]

    world = replay_world(store.read("main"))
    alice = world.entities["alice"]
    needs = alice.components["needs"]
    assert alice.active is True
    assert needs["hunger"] < 70
    assert needs["fatigue"] < 75
    assert alice.components["inventory"]["food"] == 3
    assert alice.components["health"]["current"] == 97

    # The action protocol remains replay-safe: the audit events themselves are
    # non-world events while their component_set effects carry canonical state.
    assert all_types.count("eat.resolved") == 1
    assert all_types.count("rest.resolved") == 1
