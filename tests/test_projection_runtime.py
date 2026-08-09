from worldos_core.events import NewEvent
from worldos_core.knowledge import KnowledgeProjection, replay_knowledge
from worldos_core.memory import MemoryProjection, replay_memory
from worldos_core.planning import PlannerProjection, replay_planning
from worldos_core.projection_runtime import (
    apply_knowledge_in_place,
    apply_memory_in_place,
    apply_planning_in_place,
    apply_world_in_place,
)
from worldos_core.store import InMemoryEventStore
from worldos_core.world import WorldProjection, replay_world


def _events():
    store = InMemoryEventStore()
    return store.append_batch(
        "main",
        [
            NewEvent(
                tick=0,
                phase="projection",
                event_type="entity.created",
                subject_ids=("actor",),
                payload={
                    "kind": "character",
                    "components": {
                        "position": {"location_id": "home"},
                        "health": {"current": 100, "maximum": 100},
                    },
                },
            ),
            NewEvent(
                tick=1,
                phase="cognition",
                event_type="goal.created",
                actor_id="actor",
                subject_ids=("actor",),
                payload={
                    "goal_id": "goal-1",
                    "owner_id": "actor",
                    "goal_type": "reach_location",
                    "priority": 1,
                    "parameters": {"location_id": "market"},
                    "created_tick": 1,
                },
            ),
            NewEvent(
                tick=1,
                phase="knowledge",
                event_type="observation.created",
                actor_id="actor",
                subject_ids=("actor",),
                payload={
                    "observation_id": "obs-1",
                    "observer_id": "actor",
                    "source_event_id": "source-1",
                    "tick": 1,
                    "fact_type": "location",
                    "subject_ids": ["actor"],
                    "data": {"location_id": "home"},
                    "confidence": 1.0,
                },
            ),
            NewEvent(
                tick=1,
                phase="knowledge",
                event_type="belief.updated",
                actor_id="actor",
                subject_ids=("actor",),
                payload={
                    "belief_id": "belief-1",
                    "observer_id": "actor",
                    "fact_type": "location",
                    "subject_ids": ["actor"],
                    "data": {"location_id": "home"},
                    "confidence": 1.0,
                    "source_observation_id": "obs-1",
                    "updated_tick": 1,
                },
            ),
            NewEvent(
                tick=1,
                phase="memory",
                event_type="memory.recorded",
                actor_id="actor",
                subject_ids=("actor",),
                payload={
                    "memory_id": "memory-1",
                    "owner_id": "actor",
                    "kind": "working",
                    "tick": 1,
                    "content": {"location_id": "home"},
                    "source_ids": ["belief-1"],
                    "confidence": 1.0,
                    "salience": 0.5,
                    "active": True,
                },
            ),
            NewEvent(
                tick=1,
                phase="effects",
                event_type="entity.moved",
                actor_id="actor",
                subject_ids=("actor",),
                payload={"to_location_id": "market"},
            ),
        ],
        expected_sequence=0,
    )


def test_in_place_runtime_matches_replay_projections():
    events = _events()
    world = WorldProjection()
    planning = PlannerProjection()
    memory = MemoryProjection()
    knowledge = KnowledgeProjection()

    for event in events:
        apply_world_in_place(world, event)
        apply_planning_in_place(planning, event)
        apply_memory_in_place(memory, event)
        apply_knowledge_in_place(knowledge, event)

    assert world == replay_world(events)
    assert planning == replay_planning(events)
    assert memory == replay_memory(events)
    assert knowledge == replay_knowledge(events)


def test_in_place_runtime_preserves_projection_identity():
    events = _events()
    world = WorldProjection()
    planning = PlannerProjection()
    memory = MemoryProjection()
    knowledge = KnowledgeProjection()
    identities = tuple(map(id, (world, planning, memory, knowledge)))

    for event in events:
        apply_world_in_place(world, event)
        apply_planning_in_place(planning, event)
        apply_memory_in_place(memory, event)
        apply_knowledge_in_place(knowledge, event)

    assert tuple(map(id, (world, planning, memory, knowledge))) == identities
