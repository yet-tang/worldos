from __future__ import annotations

from types import SimpleNamespace

from worldos_core.effective_memory import effective_memory_view
from worldos_core.events import NewEvent
from worldos_core.experiment_protocol import (
    ExperimentArm,
    ExperimentProtocol,
    attest_pre_treatment,
    verify_pre_treatment_attestation,
)
from worldos_core.mcp_server import _apply_memory_intervention_request, _apply_physical_checkpoint_request
from worldos_core.memory_interventions import MemoryIntervention, build_memory_intervention_event
from worldos_core.runner import WorldRunner
from worldos_core.sqlite_store import SQLiteEventStore
from worldos_core.world import replay_world
from worldos_core.world_creator import WorldCatalog, WorldConfig, compile_bootstrap_events


def _config() -> WorldConfig:
    return WorldConfig(
        name="Phase I Deterministic Lab",
        world_type="agrarian_town",
        era="agrarian",
        population=4,
        location_count=3,
        resource_abundance=55,
        social_stability=60,
        conflicts=["resource_scarcity"],
        seed="phase-i-determinism",
    )


def test_experimental_write_helpers_do_not_preempt_control_replay(monkeypatch) -> None:
    class World:
        tick = 7

        def canonical_hash(self):
            raise AssertionError("MCP must not perform a local hash guard before Control idempotency")

    monkeypatch.setattr("worldos_core.mcp_server._bundle", lambda *_: SimpleNamespace(world=World()))
    sent = []

    def inject(world_id, timeline_id, expected_hash, key, reason, event):
        sent.append((world_id, timeline_id, expected_hash, key, reason, event.event_type))
        return {"idempotency_replayed": True}

    monkeypatch.setattr("worldos_core.mcp_server._inject_experimental_event", inject)

    checkpoint = {
        "source_timeline_id": "main",
        "source_sequence": 10,
        "source_tick": 6,
        "source_world_hash": "source",
        "component_names": [],
        "actors": [],
        "physical_state_digest": "digest",
    }
    result = _apply_physical_checkpoint_request(
        "w1", checkpoint, "old-hash", "same-key", "replay", timeline_id="control"
    )
    assert result["idempotency_replayed"] is True
    assert sent[-1][:5] == ("w1", "control", "old-hash", "same-key", "replay")

    result = _apply_memory_intervention_request(
        "w1",
        {"mode": "suppress", "selector": {"experience_types": ["scarcity.perceived"]}},
        "old-hash",
        "memory-key",
        "replay",
        timeline_id="control",
    )
    assert result["idempotency_replayed"] is True
    assert sent[-1][:5] == ("w1", "control", "old-hash", "memory-key", "replay")


def test_effective_memory_view_reflects_treatment_without_advance(tmp_path) -> None:
    db = tmp_path / "memory.db"
    with SQLiteEventStore(db) as store:
        store.append_batch("main", compile_bootstrap_events(_config()), expected_sequence=0)
        current = len(store.read("main"))
        store.append_batch(
            "main",
            [
                NewEvent(
                    tick=5,
                    phase="memory",
                    event_type="memory.recorded",
                    actor_id="人物-001",
                    subject_ids=("人物-001",),
                    payload={
                        "memory_id": "m1",
                        "owner_id": "人物-001",
                        "kind": "episodic",
                        "tick": 5,
                        "content": {
                            "experience_type": "scarcity.perceived",
                            "source_tick": 4,
                            "actor_id": "人物-001",
                            "subject_ids": ["人物-001"],
                            "payload": {"pressure": 80},
                        },
                        "source_ids": ["source-1"],
                        "confidence": 1.0,
                        "salience": 0.7,
                        "active": True,
                    },
                )
            ],
            expected_sequence=current,
        )
        history = store.read("main")
        baseline = effective_memory_view(history, actor_id="人物-001", current_tick=10)
        assert baseline["effective_memory_count"] == 1
        baseline_strength = baseline["effective_memories"][0]["effective_strength"]

        current = len(history)
        store.append_batch(
            "main",
            [
                build_memory_intervention_event(
                    MemoryIntervention.model_validate(
                        {
                            "mode": "reinforce",
                            "selector": {"memory_ids": ["m1"]},
                            "multiplier": 2.0,
                        }
                    ),
                    tick=10,
                    actor_id="人物-001",
                )
            ],
            expected_sequence=current,
        )
        reinforced = effective_memory_view(store.read("main"), actor_id="人物-001", current_tick=10)
        assert reinforced["effective_memories"][0]["effective_strength"] > baseline_strength
        assert reinforced["effective_memories"][0]["intervention_event_ids"]

        current = len(store.read("main"))
        store.append_batch(
            "main",
            [
                build_memory_intervention_event(
                    MemoryIntervention.model_validate(
                        {
                            "mode": "replace",
                            "selector": {"memory_ids": ["m1"]},
                            "replacement": {
                                "experience_type": "trade.completed",
                                "source_tick": 4,
                                "subject_ids": ["人物-001", "人物-002"],
                                "payload": {"buyer_id": "人物-001", "seller_id": "人物-002"},
                            },
                        }
                    ),
                    tick=10,
                    actor_id="人物-001",
                )
            ],
            expected_sequence=current,
        )
        replaced = effective_memory_view(store.read("main"), actor_id="人物-001", current_tick=10)
        assert replaced["effective_memory_count"] == 1
        assert replaced["effective_memories"][0]["experience_type"] == "trade.completed"
        assert replaced["effective_memories"][0]["replaced"] is True


def test_post_outcome_attestation_replays_historical_equivalence(tmp_path) -> None:
    config = _config()
    treatment_db = tmp_path / "treatment.db"
    control_db = tmp_path / "control.db"
    with SQLiteEventStore(treatment_db) as treatment_store, SQLiteEventStore(control_db) as control_store:
        treatment_store.append_batch("main", compile_bootstrap_events(config), expected_sequence=0)
        control_store.append_batch("main", compile_bootstrap_events(config), expected_sequence=0)
        treatment_history = treatment_store.read("main")
        control_history = control_store.read("main")
        treatment_world = replay_world(treatment_history)
        control_world = replay_world(control_history)
        protocol = ExperimentProtocol(
            checkpoint_digest="checkpoint-1",
            treatment=ExperimentArm("treatment", "treatment", {"memory.scarcity": "retain"}),
            control=ExperimentArm("control", "control", {"memory.scarcity": "suppress"}),
        )
        attestation = attest_pre_treatment(
            protocol,
            treatment_world,
            control_world,
            treatment_event_count=len(treatment_history),
            control_event_count=len(control_history),
        )
        assert attestation.valid_for_causal_run is True

        treatment_store.append_batch(
            "main",
            [NewEvent(tick=0, phase="experiment", event_type="entity.component_set", actor_id="人物-001", subject_ids=("人物-001",), payload={"component": "wallet", "value": 999})],
            expected_sequence=len(treatment_history),
        )
        control_store.append_batch(
            "main",
            [NewEvent(tick=0, phase="experiment", event_type="entity.component_set", actor_id="人物-001", subject_ids=("人物-001",), payload={"component": "wallet", "value": 1})],
            expected_sequence=len(control_history),
        )
        verified = verify_pre_treatment_attestation(
            protocol,
            attestation,
            treatment_history=treatment_store.read("main"),
            control_history=control_store.read("main"),
        )
        assert verified["attestation_verified"] is True
        assert verified["valid_for_causal_run"] is True

        tampered = attestation.model_copy(update={"treatment_world_hash": "tampered"})
        rejected = verify_pre_treatment_attestation(
            protocol,
            tampered,
            treatment_history=treatment_store.read("main"),
            control_history=control_store.read("main"),
        )
        assert rejected["attestation_verified"] is False
        assert rejected["valid_for_causal_run"] is False


def test_identical_cross_world_runtime_produces_identical_hash(tmp_path) -> None:
    catalog = WorldCatalog(tmp_path)
    first = catalog.create(_config())
    second = catalog.create(_config())
    with WorldRunner(first.database_path, world_seed=first.seed, snapshot_interval=0) as left:
        left_result = left.run(3)
    with WorldRunner(second.database_path, world_seed=second.seed, snapshot_interval=0) as right:
        right_result = right.run(3)
    assert left_result.status.event_count == right_result.status.event_count
    assert left_result.status.world_hash == right_result.status.world_hash
