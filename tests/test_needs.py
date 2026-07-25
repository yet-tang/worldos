from worldos_core.events import NewEvent
from worldos_core.needs import NeedEngine, replay_needs
from worldos_core.planning import replay_planning
from worldos_core.scheduler import DeterministicTickEngine
from worldos_core.store import InMemoryEventStore
from worldos_core.world import replay_world


def _seed_hungry_actor(store: InMemoryEventStore) -> None:
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
                        "position": {"location_id": "home"},
                        "needs": {"hunger": 85},
                        "need_policies": {
                            "hunger": {
                                "threshold": 60,
                                "goal_type": "reach_location",
                                "parameters": {"location_id": "market"},
                            }
                        },
                    },
                },
            )
        ],
        expected_sequence=0,
    )


def test_need_assessment_creates_goal_and_drives_intent():
    store = InMemoryEventStore()
    _seed_hungry_actor(store)

    result = DeterministicTickEngine(store, world_seed="seed").run_tick("main", 1)
    event_types = [event.event_type for event in result.committed_events]

    assert "need.assessed" in event_types
    assert "goal.created" in event_types
    assert "plan.step_created" in event_types
    assert "entity.moved" in event_types
    assert replay_world(store.read("main")).entities["alice"].components["position"]["location_id"] == "market"


def test_need_projection_keeps_latest_assessment():
    store = InMemoryEventStore()
    _seed_hungry_actor(store)
    engine = DeterministicTickEngine(store, world_seed="seed")
    engine.run_tick("main", 1)

    needs = replay_needs(store.read("main"))
    assessment = needs.assessments("alice")[0]
    assert assessment.need_type == "hunger"
    assert assessment.severity == 85
    assert assessment.threshold == 60


def test_active_need_goal_is_not_duplicated():
    store = InMemoryEventStore()
    _seed_hungry_actor(store)
    world = replay_world(store.read("main"))
    planning = replay_planning(store.read("main"))
    engine = NeedEngine()

    first = engine.derive(world, planning, tick=1)
    goal_event = next(event for event in first if event.event_type == "goal.created")
    store.append_batch("main", first, expected_sequence=len(store.read("main")))

    planning = replay_planning(store.read("main"))
    second = engine.derive(world, planning, tick=2)
    assert goal_event.payload["parameters"]["source_need"] == "hunger"
    assert [event for event in second if event.event_type == "goal.created"] == []


def test_needs_are_deterministic_for_same_state_and_tick():
    first = InMemoryEventStore()
    second = InMemoryEventStore()
    _seed_hungry_actor(first)
    _seed_hungry_actor(second)

    left = DeterministicTickEngine(first, world_seed="seed").run_tick("main", 1)
    right = DeterministicTickEngine(second, world_seed="seed").run_tick("main", 1)

    assert [event.model_dump(mode="json") for event in left.committed_events] == [
        event.model_dump(mode="json") for event in right.committed_events
    ]
