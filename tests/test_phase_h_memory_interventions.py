import pytest

from worldos_core.adaptive import AdaptiveMemoryModule
from worldos_core.events import Event
from worldos_core.memory_interventions import MemoryIntervention, MemorySelector, build_memory_intervention_event


def committed(new_event, *, sequence: int, event_id: str, timeline_id: str = "treatment") -> Event:
    return Event(
        sequence=sequence,
        event_id=event_id,
        timeline_id=timeline_id,
        tick=new_event.tick,
        phase=new_event.phase,
        event_type=new_event.event_type,
        schema_version=new_event.schema_version,
        actor_id=new_event.actor_id,
        subject_ids=new_event.subject_ids,
        caused_by=new_event.caused_by,
        correlation_id=new_event.correlation_id,
        payload=new_event.payload,
        metadata=new_event.metadata,
    )


def memory_event(*, sequence: int = 1, event_id: str = "memory-1") -> Event:
    return Event(
        sequence=sequence,
        event_id=event_id,
        timeline_id="treatment",
        tick=10,
        phase="memory",
        event_type="memory.recorded",
        actor_id="人物-001",
        subject_ids=("人物-001",),
        payload={
            "memory_id": "mem-scarcity-1",
            "owner_id": "人物-001",
            "kind": "episodic",
            "tick": 10,
            "content": {
                "experience_type": "scarcity.perceived",
                "source_tick": 9,
                "actor_id": "人物-001",
                "subject_ids": ["人物-001"],
                "payload": {"pressure": 90},
            },
            "confidence": 1.0,
            "salience": 0.7,
            "active": True,
        },
    )


def test_suppress_keeps_raw_memory_but_removes_adaptive_influence():
    raw = memory_event()
    intervention = build_memory_intervention_event(
        MemoryIntervention(
            mode="suppress",
            selector=MemorySelector(memory_ids=("mem-scarcity-1",)),
            reason="causal control",
        ),
        tick=11,
        actor_id="人物-001",
    )
    history = (raw, committed(intervention, sequence=2, event_id="intervention-1"))
    memories = AdaptiveMemoryModule._experience_memories(history)
    assert raw in history
    assert memories["人物-001"] == []
    strategy = AdaptiveMemoryModule._strategy("人物-001", memories["人物-001"], current_tick=12)
    assert strategy["reserve_bonus"] == 0
    assert strategy["experience_count"] == 0


def test_reinforce_multiplies_effective_strength_without_duplicating_memory():
    raw = memory_event()
    baseline = AdaptiveMemoryModule._experience_memories((raw,))["人物-001"]
    baseline_strength = AdaptiveMemoryModule._memory_strength(baseline[0], current_tick=20, repetition_count=1)

    intervention = build_memory_intervention_event(
        MemoryIntervention(
            mode="reinforce",
            selector=MemorySelector(experience_types=("scarcity.perceived",)),
            multiplier=2.0,
            reason="experimental reinforcement",
        ),
        tick=11,
        actor_id="人物-001",
    )
    history = (raw, committed(intervention, sequence=2, event_id="intervention-2"))
    treated = AdaptiveMemoryModule._experience_memories(history)["人物-001"]
    treated_strength = AdaptiveMemoryModule._memory_strength(treated[0], current_tick=20, repetition_count=1)
    assert len(treated) == 1
    assert treated_strength == pytest.approx(baseline_strength * 2.0, abs=0.0001)
    strategy = AdaptiveMemoryModule._strategy("人物-001", treated, current_tick=20)
    assert strategy["evidence"]["treated_memory_count"] == 1


def test_replace_preserves_audit_source_but_changes_effective_experience_type():
    raw = memory_event()
    intervention = build_memory_intervention_event(
        MemoryIntervention(
            mode="replace",
            selector=MemorySelector(memory_ids=("mem-scarcity-1",)),
            replacement={
                "experience_type": "trade.completed",
                "subject_ids": ["人物-001", "人物-002"],
                "payload": {"seller_id": "人物-002", "buyer_id": "人物-001"},
            },
            reason="counterfactual memory treatment",
        ),
        tick=11,
        actor_id="人物-001",
    )
    history = (raw, committed(intervention, sequence=2, event_id="intervention-3"))
    memories = AdaptiveMemoryModule._experience_memories(history)["人物-001"]
    assert len(memories) == 1
    assert memories[0]["memory_id"] == "mem-scarcity-1"
    assert memories[0]["replaced"] is True
    assert memories[0]["content"]["experience_type"] == "trade.completed"
    strategy = AdaptiveMemoryModule._strategy("人物-001", memories, current_tick=12)
    assert strategy["preferred_partners"] == ["人物-002"]
