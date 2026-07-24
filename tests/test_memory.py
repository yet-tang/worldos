from worldos_core.events import Event
from worldos_core.knowledge import Belief, KnowledgeProjection
from worldos_core.memory import MemoryEngine, MemoryPolicy, replay_memory


def _commit(events):
    return [Event(**event.model_dump(), event_id=f"evt_{index}", timeline_id="main", sequence=index) for index, event in enumerate(events, start=1)]


def test_memory_engine_derives_layered_records():
    knowledge = KnowledgeProjection(
        beliefs_by_observer={
            "alice": {
                "belief_1": Belief(
                    belief_id="belief_1",
                    observer_id="alice",
                    fact_type="attack.resolved",
                    subject_ids=("bob",),
                    data={"hit": True},
                    confidence=0.9,
                    source_observation_id="obs_1",
                    updated_tick=3,
                )
            }
        }
    )
    events = MemoryEngine().derive(knowledge, tick=4)
    assert [event.payload["kind"] for event in events] == ["working", "episodic", "semantic"]


def test_identity_belief_creates_identity_memory():
    knowledge = KnowledgeProjection(
        beliefs_by_observer={
            "alice": {
                "belief_role": Belief(
                    belief_id="belief_role",
                    observer_id="alice",
                    fact_type="role",
                    subject_ids=("alice",),
                    data={"role": "keeper"},
                    confidence=0.7,
                    source_observation_id="obs_role",
                    updated_tick=1,
                )
            }
        }
    )
    events = MemoryEngine().derive(knowledge, tick=2)
    assert "identity" in [event.payload["kind"] for event in events]


def test_working_memory_capacity_expires_oldest_record():
    policy = MemoryPolicy(working_capacity=2)
    events = []
    for index in range(3):
        events.append(
            MemoryEngine._event(
                "alice", f"mem_{index}", "working", index, {"index": index}, (f"belief_{index}",), 1.0, 0.5
            )
        )
    state = replay_memory(_commit(events), policy=policy)
    assert not state.records_by_owner["alice"]["mem_0"].active
    assert [record.memory_id for record in state.memories("alice", "working")] == ["mem_1", "mem_2"]


def test_memory_replay_is_deterministic():
    event = MemoryEngine._event("alice", "mem_1", "episodic", 5, {"fact": "snow"}, ("belief_1",), 0.8, 0.7)
    committed = _commit([event])
    assert replay_memory(committed).model_dump() == replay_memory(committed).model_dump()
