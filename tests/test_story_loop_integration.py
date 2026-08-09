from worldos_core.events import NewEvent
from worldos_core.motivation import MotivationEngine
from worldos_core.planning import PlannerProjection
from worldos_core.scheduler import DeterministicTickEngine
from worldos_core.store import InMemoryEventStore
from worldos_core.world import replay_world


def _character(
    actor_id: str,
    *,
    food: int,
    hunger: int,
    personality: dict[str, int],
    drives: dict[str, int],
) -> NewEvent:
    return NewEvent(
        tick=0,
        phase="bootstrap",
        event_type="entity.created",
        subject_ids=(actor_id,),
        payload={
            "kind": "character",
            "components": {
                "identity": {"name": actor_id},
                "position": {"location_id": "集市"},
                "health": {"current": 100, "maximum": 100},
                "needs": {"hunger": hunger, "fatigue": 10},
                "survival": {"hunger": hunger, "fatigue": 10},
                "inventory": {"food": food},
                "relationships": {},
                "personality": personality,
                "drives": drives,
            },
        },
    )


def test_autonomous_care_motivation_changes_world_and_is_observed():
    quiet_personality = {
        "sociability": 0,
        "generosity": 0,
        "assertiveness": 0,
        "risk_tolerance": 0,
    }
    quiet_drives = {
        "security": 0,
        "belonging": 0,
        "status": 0,
        "wealth": 0,
        "curiosity": 0,
    }
    store = InMemoryEventStore()
    store.append_batch(
        "main",
        [
            _character(
                "甲",
                food=5,
                hunger=20,
                personality={
                    "sociability": 20,
                    "generosity": 100,
                    "assertiveness": 10,
                    "risk_tolerance": 10,
                },
                drives={
                    "security": 20,
                    "belonging": 10,
                    "status": 10,
                    "wealth": 10,
                    "curiosity": 10,
                },
            ),
            _character("乙", food=2, hunger=60, personality=quiet_personality, drives=quiet_drives),
            _character("丙", food=2, hunger=20, personality=quiet_personality, drives=quiet_drives),
        ],
        expected_sequence=0,
    )
    motivation = MotivationEngine()
    engine = DeterministicTickEngine(store, world_seed="seed", motivation=motivation)
    due_tick = next(
        tick
        for tick in range(1, 4)
        if motivation._due("worldos:甲", tick)
    )

    for tick in range(1, due_tick + 1):
        engine.run_tick("main", tick)

    history = store.read("main")
    selected = [
        event
        for event in history
        if event.event_type == "motivation.selected" and event.actor_id == "甲"
    ]
    helped = [
        event
        for event in history
        if event.event_type == "social.helped" and event.actor_id == "甲"
    ]
    world = replay_world(history)

    assert selected[-1].payload["goal_type"] == "help_resident"
    assert helped
    assert world.entities["甲"].components["inventory"]["food"] == 4
    assert world.entities["乙"].components["inventory"]["food"] == 3
    assert world.entities["甲"].components["relationships"]["乙"] > 0
    assert world.entities["乙"].components["relationships"]["甲"] > 0
    assert any(
        event.event_type == "observation.created"
        and event.actor_id == "丙"
        and event.payload.get("fact_type") == "social.helped"
        for event in history
    )
    assert any(
        event.event_type == "memory.recorded"
        and event.actor_id == "丙"
        and event.payload.get("content", {}).get("fact_type") == "social.helped"
        for event in history
    )


def test_urgent_survival_preempts_social_and_exploration_motivation():
    store = InMemoryEventStore()
    store.append_batch(
        "main",
        [
            _character(
                "甲",
                food=5,
                hunger=70,
                personality={
                    "sociability": 100,
                    "generosity": 100,
                    "assertiveness": 100,
                    "risk_tolerance": 100,
                },
                drives={
                    "security": 100,
                    "belonging": 100,
                    "status": 100,
                    "wealth": 100,
                    "curiosity": 100,
                },
            ),
            _character(
                "乙",
                food=2,
                hunger=60,
                personality={"sociability": 0, "generosity": 0, "assertiveness": 0, "risk_tolerance": 0},
                drives={"security": 0, "belonging": 0, "status": 0, "wealth": 0, "curiosity": 0},
            ),
        ],
        expected_sequence=0,
    )
    world = replay_world(store.read("main"))
    events = MotivationEngine().derive(world, PlannerProjection(), tick=1)

    assert not [
        event
        for event in events
        if event.actor_id == "甲" and event.event_type in {"motivation.considered", "motivation.selected", "goal.created"}
    ]
