from worldos_core import InMemoryEventStore, NewEvent, WorldInspector


def seed_store() -> InMemoryEventStore:
    store = InMemoryEventStore()
    committed = store.append_batch(
        "main",
        [
            NewEvent(tick=0, phase="world", event_type="world.created", payload={"flags": {"seed": 7}}),
            NewEvent(
                tick=0,
                phase="world",
                event_type="entity.created",
                actor_id="hero",
                subject_ids=("hero",),
                payload={"kind": "character", "components": {"position": {"location_id": "town"}}},
            ),
        ],
    )
    observation = store.append_batch(
        "main",
        [
            NewEvent(
                tick=1,
                phase="observation",
                event_type="observation.created",
                actor_id="hero",
                subject_ids=("hero",),
                caused_by=(committed[1].event_id,),
                payload={
                    "observation_id": "obs_1",
                    "observer_id": "hero",
                    "source_event_id": committed[1].event_id,
                    "tick": 1,
                    "fact_type": "entity.created",
                    "subject_ids": ("hero",),
                    "data": {"kind": "character"},
                    "confidence": 1.0,
                },
            )
        ],
    )[0]
    store.append_batch(
        "main",
        [
            NewEvent(
                tick=1,
                phase="knowledge",
                event_type="belief.updated",
                actor_id="hero",
                subject_ids=("hero",),
                caused_by=(observation.event_id,),
                payload={
                    "belief_id": "belief_1",
                    "observer_id": "hero",
                    "fact_type": "entity.created",
                    "subject_ids": ("hero",),
                    "data": {"kind": "character"},
                    "confidence": 1.0,
                    "source_observation_id": "obs_1",
                    "updated_tick": 1,
                },
            ),
            NewEvent(
                tick=1,
                phase="memory",
                event_type="memory.recorded",
                actor_id="hero",
                subject_ids=("hero",),
                payload={
                    "memory_id": "mem_1",
                    "owner_id": "hero",
                    "kind": "working",
                    "tick": 1,
                    "content": {"fact": "exists"},
                    "source_ids": ("belief_1",),
                    "confidence": 1.0,
                    "salience": 0.5,
                    "active": True,
                },
            ),
            NewEvent(
                tick=1,
                phase="planning",
                event_type="goal.created",
                actor_id="hero",
                subject_ids=("hero",),
                payload={
                    "goal_id": "goal_1",
                    "owner_id": "hero",
                    "goal_type": "reach_location",
                    "priority": 5,
                    "parameters": {"location_id": "forest"},
                    "created_tick": 1,
                },
            ),
        ],
    )
    return store


def test_snapshot_supports_historical_replay() -> None:
    inspector = WorldInspector(seed_store())
    early = inspector.snapshot(through_sequence=2)
    current = inspector.snapshot()
    assert early.event_count == 2
    assert current.event_count == 6
    assert early.world_hash == current.world_hash
    assert early.world.entities["hero"].components["position"]["location_id"] == "town"


def test_actor_view_combines_world_and_cognitive_projections() -> None:
    view = WorldInspector(seed_store()).actor("hero")
    assert view.entity is not None
    assert [item.observation_id for item in view.observations] == ["obs_1"]
    assert [item.belief_id for item in view.beliefs] == ["belief_1"]
    assert [item.memory_id for item in view.memories] == ["mem_1"]
    assert [item.goal_id for item in view.goals] == ["goal_1"]


def test_event_filters_and_causality_are_read_only() -> None:
    store = seed_store()
    inspector = WorldInspector(store)
    observations = inspector.events(event_type="observation.created", actor_id="hero", tick=1)
    explanation = inspector.explain_event(observations[0].event_id)
    assert len(observations) == 1
    assert explanation is not None
    assert explanation["causes"][0].event_type == "entity.created"
    assert len(store.read("main")) == 6


def test_branch_snapshot_inherits_parent_history() -> None:
    store = seed_store()
    store.create_timeline("what-if", parent_through_sequence=2)
    store.append_batch(
        "what-if",
        [NewEvent(tick=2, phase="world", event_type="world.flag_set", payload={"name": "branch", "value": True})],
    )
    snapshot = WorldInspector(store).snapshot("what-if")
    assert snapshot.event_count == 3
    assert snapshot.world.flags["branch"] is True
