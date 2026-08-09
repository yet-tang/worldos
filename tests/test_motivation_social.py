from worldos_core.events import NewEvent
from worldos_core.motivation import MotivationEngine
from worldos_core.planning import Goal, PlannerProjection
from worldos_core.scheduler import DeterministicTickEngine
from worldos_core.store import InMemoryEventStore
from worldos_core.world import WorldProjection, replay_world


def _actor(
    entity_id: str,
    *,
    location: str = "集市",
    food: int = 2,
    hunger: int = 20,
    relationships: dict[str, int] | None = None,
    personality: dict[str, int] | None = None,
    drives: dict[str, int] | None = None,
) -> NewEvent:
    return NewEvent(
        tick=0,
        phase="bootstrap",
        event_type="entity.created",
        subject_ids=(entity_id,),
        payload={
            "kind": "character",
            "components": {
                "identity": {"name": entity_id},
                "position": {"location_id": location},
                "health": {"current": 100, "maximum": 100},
                "needs": {"hunger": hunger, "fatigue": 10},
                "survival": {"hunger": hunger, "fatigue": 10},
                "inventory": {"food": food},
                "relationships": relationships or {},
                **({"personality": personality} if personality else {}),
                **({"drives": drives} if drives else {}),
            },
        },
    )


def _due_tick(engine: MotivationEngine, actor_id: str) -> int:
    return next(tick for tick in range(1, 4) if engine._due(actor_id, tick))


def test_motivation_competes_and_selects_contextual_goal():
    engine = MotivationEngine()
    world = WorldProjection()
    store = InMemoryEventStore()
    store.append_batch(
        "main",
        [
            _actor(
                "甲",
                food=5,
                personality={"sociability": 100, "generosity": 100, "assertiveness": 40, "risk_tolerance": 50},
                drives={"security": 50, "belonging": 100, "status": 40, "wealth": 50, "curiosity": 50},
            ),
            _actor("乙", food=0, hunger=60),
        ],
        expected_sequence=0,
    )
    world = replay_world(store.read("main"))
    tick = _due_tick(engine, "甲")

    events = engine.derive(world, PlannerProjection(), tick=tick)
    considered = [event for event in events if event.event_type == "motivation.considered" and event.actor_id == "甲"]
    selected = [event for event in events if event.event_type == "motivation.selected" and event.actor_id == "甲"]

    assert {event.payload["goal_type"] for event in considered} >= {"help_resident", "strengthen_relationship"}
    assert selected[0].payload["goal_type"] == "help_resident"
    goal = next(event for event in events if event.event_type == "goal.created" and event.actor_id == "甲")
    assert goal.payload["parameters"]["source_motivation"] == "care"


def test_profiles_are_materialized_for_legacy_characters():
    store = InMemoryEventStore()
    store.append_batch("main", [_actor("甲"), _actor("乙")], expected_sequence=0)
    engine = DeterministicTickEngine(store, world_seed="seed")
    engine.run_tick("main", 1)

    world = replay_world(store.read("main"))
    assert set(world.entities["甲"].components["personality"]) == {
        "sociability",
        "generosity",
        "assertiveness",
        "risk_tolerance",
    }
    assert set(world.entities["甲"].components["drives"]) == {
        "security",
        "belonging",
        "status",
        "wealth",
        "curiosity",
    }
    assert world.entities["甲"].components["personality"] != world.entities["乙"].components["personality"]


def test_social_goal_moves_then_interacts_and_completes():
    store = InMemoryEventStore()
    store.append_batch(
        "main",
        [
            _actor("甲", location="农田", relationships={"乙": 0}),
            _actor("乙", location="集市", relationships={"甲": 0}),
            NewEvent(
                tick=0,
                phase="cognition",
                event_type="goal.created",
                actor_id="甲",
                subject_ids=("甲",),
                payload=Goal(
                    goal_id="social-goal",
                    owner_id="甲",
                    goal_type="strengthen_relationship",
                    priority=99,
                    parameters={"target_id": "乙", "source_motivation": "belonging"},
                ).model_dump(mode="json"),
            ),
        ],
        expected_sequence=0,
    )
    engine = DeterministicTickEngine(store, world_seed="seed")
    first = engine.run_tick("main", 1)
    assert "entity.moved" in [event.event_type for event in first.committed_events]
    assert replay_world(store.read("main")).entities["甲"].components["position"]["location_id"] == "集市"

    second = engine.run_tick("main", 2)
    types = [event.event_type for event in second.committed_events]
    assert "social.interacted" in types
    world = replay_world(store.read("main"))
    assert world.entities["甲"].components["relationships"]["乙"] > 0
    assert world.entities["乙"].components["relationships"]["甲"] > 0
    completed = [
        event
        for event in second.committed_events
        if event.event_type == "goal.status_changed" and event.payload.get("goal_id") == "social-goal"
    ]
    assert completed[-1].payload["status"] == "completed"


def test_help_action_changes_resources_relationships_and_is_perceived():
    store = InMemoryEventStore()
    store.append_batch(
        "main",
        [
            _actor(
                "甲",
                food=5,
                relationships={"乙": 0},
                personality={"sociability": 80, "generosity": 100, "assertiveness": 30, "risk_tolerance": 50},
                drives={"security": 50, "belonging": 40, "status": 30, "wealth": 40, "curiosity": 40},
            ),
            _actor("乙", food=0, hunger=60, relationships={"甲": 0}),
            _actor("丙", food=2, hunger=20),
        ],
        expected_sequence=0,
    )
    motivation = MotivationEngine()
    engine = DeterministicTickEngine(store, world_seed="seed", motivation=motivation)
    due = _due_tick(motivation, "甲")
    for tick in range(1, due + 1):
        engine.run_tick("main", tick)

    history = store.read("main")
    help_events = [event for event in history if event.event_type == "social.helped" and event.actor_id == "甲"]
    assert help_events
    world = replay_world(history)
    assert world.entities["甲"].components["inventory"]["food"] == 4
    assert world.entities["乙"].components["inventory"]["food"] == 1
    assert world.entities["乙"].components["relationships"]["甲"] > 0
    assert any(
        event.event_type == "observation.created"
        and event.actor_id == "丙"
        and event.payload.get("fact_type") == "social.helped"
        for event in history
    )
