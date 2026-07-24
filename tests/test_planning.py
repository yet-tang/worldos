from worldos_core.events import NewEvent
from worldos_core.memory import MemoryProjection
from worldos_core.planning import GoalPlanner, PlanningContext, replay_planning
from worldos_core.store import InMemoryEventStore
from worldos_core.world import replay_world


def _commit(store, events):
    return store.append_batch("main", events, expected_sequence=len(store.read("main")))


def _world(store):
    return replay_world(store.read("main"))


def test_selects_highest_priority_active_goal():
    store = InMemoryEventStore()
    events = _commit(store, [
        NewEvent(tick=1, phase="cognition", event_type="goal.created", actor_id="hero", subject_ids=("hero",), payload={"goal_id":"g1","owner_id":"hero","goal_type":"reach_location","priority":1,"parameters":{"location_id":"inn"},"created_tick":1}),
        NewEvent(tick=1, phase="cognition", event_type="goal.created", actor_id="hero", subject_ids=("hero",), payload={"goal_id":"g2","owner_id":"hero","goal_type":"defeat_entity","priority":9,"parameters":{"target_id":"bandit"},"created_tick":1}),
    ])
    projection = replay_planning(events)
    assert GoalPlanner().choose_goal(projection, "hero").goal_id == "g2"


def test_plans_reach_location_and_emits_intent():
    store = InMemoryEventStore()
    committed = _commit(store, [
        NewEvent(tick=1, phase="projection", event_type="entity.created", subject_ids=("hero",), payload={"kind":"character","components":{"position":{"location_id":"road"}}}),
        NewEvent(tick=2, phase="cognition", event_type="goal.created", actor_id="hero", subject_ids=("hero",), payload={"goal_id":"g1","owner_id":"hero","goal_type":"reach_location","priority":5,"parameters":{"location_id":"inn"},"created_tick":2}),
    ])
    planning = replay_planning(committed)
    planner = GoalPlanner()
    context = PlanningContext(owner_id="hero", tick=3, world=_world(store), memory=MemoryProjection())
    plan_events = planner.plan(planner.choose_goal(planning, "hero"), context)
    committed += _commit(store, plan_events)
    planning = replay_planning(committed)
    intent = planner.next_intent(planning, context)
    assert intent.intent_type == "move"
    assert intent.parameters == {"to_location_id": "inn"}
    assert intent.correlation_id == "g1"


def test_planner_is_deterministic():
    store = InMemoryEventStore()
    committed = _commit(store, [
        NewEvent(tick=1, phase="cognition", event_type="goal.created", actor_id="hero", subject_ids=("hero",), payload={"goal_id":"g1","owner_id":"hero","goal_type":"defeat_entity","priority":5,"parameters":{"target_id":"bandit"},"created_tick":1}),
    ])
    planning = replay_planning(committed)
    context = PlanningContext(owner_id="hero", tick=2, world=_world(store), memory=MemoryProjection())
    planner = GoalPlanner()
    goal = planner.choose_goal(planning, "hero")
    first = planner.plan(goal, context)
    second = planner.plan(goal, context)
    assert [event.model_dump(mode="json") for event in first] == [event.model_dump(mode="json") for event in second]


def test_defeat_goal_maps_target_to_intent_target():
    store = InMemoryEventStore()
    committed = _commit(store, [
        NewEvent(tick=1, phase="cognition", event_type="goal.created", actor_id="hero", subject_ids=("hero",), payload={"goal_id":"g1","owner_id":"hero","goal_type":"defeat_entity","priority":5,"parameters":{"target_id":"bandit"},"created_tick":1}),
    ])
    planning = replay_planning(committed)
    context = PlanningContext(owner_id="hero", tick=2, world=_world(store), memory=MemoryProjection())
    planner = GoalPlanner()
    committed += _commit(store, planner.plan(planner.choose_goal(planning, "hero"), context))
    intent = planner.next_intent(replay_planning(committed), context)
    assert intent.intent_type == "attack"
    assert intent.target_id == "bandit"
    assert intent.parameters == {}


def test_survive_goal_uses_current_world_state():
    store = InMemoryEventStore()
    committed = _commit(store, [
        NewEvent(tick=1, phase="projection", event_type="entity.created", subject_ids=("hero",), payload={"kind":"character","components":{"health":{"current":30,"maximum":100}}}),
        NewEvent(tick=2, phase="cognition", event_type="goal.created", actor_id="hero", subject_ids=("hero",), payload={"goal_id":"survive","owner_id":"hero","goal_type":"survive","priority":10,"parameters":{"safe_location_id":"inn"},"created_tick":2}),
    ])
    planning = replay_planning(committed)
    context = PlanningContext(owner_id="hero", tick=3, world=_world(store), memory=MemoryProjection())
    planner = GoalPlanner()
    plan_events = planner.plan(planner.choose_goal(planning, "hero"), context)
    assert plan_events[0].payload["action_type"] == "move"
    assert plan_events[0].payload["arguments"]["to_location_id"] == "inn"
