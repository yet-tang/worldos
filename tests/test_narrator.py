from worldos_core import InMemoryEventStore, NarratorReadAPI, NewEvent, WorldInspector


def seed_store() -> InMemoryEventStore:
    store = InMemoryEventStore()
    committed = store.append_batch(
        "main",
        [
            NewEvent(tick=0, phase="world", event_type="world.created", payload={"flags": {}}),
            NewEvent(
                tick=0,
                phase="world",
                event_type="entity.created",
                actor_id="hero",
                subject_ids=("hero",),
                payload={"kind": "character", "components": {"position": {"location_id": "town"}}},
            ),
            NewEvent(
                tick=0,
                phase="world",
                event_type="entity.created",
                actor_id="villain",
                subject_ids=("villain",),
                payload={"kind": "character", "components": {"position": {"location_id": "castle"}}},
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
                    "observation_id": "obs_hero",
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
                    "belief_id": "belief_hero",
                    "observer_id": "hero",
                    "fact_type": "entity.created",
                    "subject_ids": ("hero",),
                    "data": {"kind": "character"},
                    "confidence": 1.0,
                    "source_observation_id": "obs_hero",
                    "updated_tick": 1,
                },
            )
        ],
    )
    return store


def test_omniscient_context_reads_all_visible_events() -> None:
    store = seed_store()
    context = NarratorReadAPI(WorldInspector(store)).context()
    assert context.mode == "omniscient"
    assert context.world_hash is not None
    assert [event.sequence for event in context.events] == [1, 2, 3, 4, 5]
    assert len(store.read("main")) == 5


def test_actor_context_exposes_only_observed_source_events() -> None:
    context = NarratorReadAPI(WorldInspector(seed_store())).context(perspective_actor_id="hero")
    assert context.mode == "actor"
    assert context.world_hash is None
    assert [event.event_type for event in context.events] == ["entity.created"]
    assert [event.actor_id for event in context.events] == ["hero"]
    assert [item.observation_id for item in context.observations] == ["obs_hero"]
    assert [item.belief_id for item in context.beliefs] == ["belief_hero"]


def test_actor_context_does_not_leak_unobserved_world_truth() -> None:
    context = NarratorReadAPI(WorldInspector(seed_store())).context(perspective_actor_id="hero")
    assert all("villain" not in event.subject_ids for event in context.events)
    assert all("castle" not in str(event.payload) for event in context.events)


def test_context_supports_historical_and_sequence_windows() -> None:
    narrator = NarratorReadAPI(WorldInspector(seed_store()))
    context = narrator.context(through_sequence=3, from_sequence=2)
    assert context.through_sequence == 3
    assert [event.sequence for event in context.events] == [2, 3]
