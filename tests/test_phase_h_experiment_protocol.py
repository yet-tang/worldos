from worldos_core.experiment_protocol import ExperimentArm, ExperimentProtocol, causal_report, validate_pre_treatment
from worldos_core.world import EntityProjection, WorldProjection


def make_world(*, food: int, reserve_bonus: int, seed: str = "phase-h") -> WorldProjection:
    return WorldProjection(
        tick=20,
        flags={"seed": seed},
        entities={
            "人物-001": EntityProjection(
                entity_id="人物-001",
                kind="character",
                components={
                    "inventory": {"food": food},
                    "wallet": 10,
                    "health": {"current": 100, "maximum": 100},
                    "needs": {"hunger": 20, "fatigue": 10},
                    "survival": {"hunger": 20, "fatigue": 10},
                    "position": {"location_id": "集市"},
                    "food_security": {"food": food, "target_reserve": 5, "shortage": max(0, 5-food), "pressure": 20},
                    "adaptive_strategy": {"reserve_bonus": reserve_bonus},
                },
            )
        },
    )


def make_protocol() -> ExperimentProtocol:
    return ExperimentProtocol(
        checkpoint_digest="checkpoint-001",
        treatment=ExperimentArm(
            name="experienced",
            timeline_id="treatment",
            declared_intervention={"memory.scarcity": "retain"},
        ),
        control=ExperimentArm(
            name="naive",
            timeline_id="control",
            declared_intervention={"memory.scarcity": "suppress"},
        ),
    )


def probe(timeline: str, *, food: int, hunger: int, events: int) -> dict:
    return {
        "snapshot": {"timeline_id": timeline, "current_tick": 30, "event_count": events, "world_hash": f"hash-{timeline}"},
        "actors": [
            {
                "actor_id": "人物-001",
                "inventory": {"food": food},
                "wallet": 10,
                "needs": {"hunger": hunger, "fatigue": 10},
                "health": {"current": 100, "maximum": 100},
                "rumors": [],
            }
        ],
        "recent_events": [],
    }


def test_protocol_accepts_identical_physical_state_with_different_memory_treatment():
    treatment = make_world(food=8, reserve_bonus=6)
    control = make_world(food=8, reserve_bonus=0)
    result = validate_pre_treatment(make_protocol(), treatment, control)
    assert result["physical_state_equal"] is True
    assert result["seed_equal"] is True
    assert result["intentional_intervention_difference"] is True
    assert result["valid_for_causal_run"] is True


def test_protocol_rejects_hidden_physical_difference():
    treatment = make_world(food=8, reserve_bonus=6)
    control = make_world(food=7, reserve_bonus=0)
    result = validate_pre_treatment(make_protocol(), treatment, control)
    assert result["physical_state_equal"] is False
    assert result["valid_for_causal_run"] is False


def test_protocol_requires_an_intentional_intervention_difference():
    protocol = ExperimentProtocol(
        checkpoint_digest="checkpoint-001",
        treatment=ExperimentArm(name="a", timeline_id="a", declared_intervention={"memory.scarcity": "retain"}),
        control=ExperimentArm(name="b", timeline_id="b", declared_intervention={"memory.scarcity": "retain"}),
    )
    result = validate_pre_treatment(protocol, make_world(food=8, reserve_bonus=6), make_world(food=8, reserve_bonus=0))
    assert result["intentional_intervention_difference"] is False
    assert result["valid_for_causal_run"] is False


def test_causal_report_carries_declared_treatment_and_metric_delta():
    protocol = make_protocol()
    pre = validate_pre_treatment(protocol, make_world(food=8, reserve_bonus=6), make_world(food=8, reserve_bonus=0))
    report = causal_report(
        protocol,
        pre_treatment=pre,
        treatment_probe=probe("treatment", food=5, hunger=35, events=140),
        control_probe=probe("control", food=7, hunger=30, events=130),
        outcome_names=("average_hunger", "inventory_totals"),
    )
    assert report["attribution"]["eligible"] is True
    assert report["selected_outcomes"]["average_hunger"] == 5.0
    assert report["selected_outcomes"]["inventory_totals"]["food"] == -2.0
    assert report["protocol"]["treatment"]["intervention"] == {"memory.scarcity": "retain"}


def test_causal_report_refuses_attribution_when_equivalence_failed():
    protocol = make_protocol()
    pre = validate_pre_treatment(protocol, make_world(food=8, reserve_bonus=6), make_world(food=7, reserve_bonus=0))
    report = causal_report(
        protocol,
        pre_treatment=pre,
        treatment_probe=probe("treatment", food=5, hunger=35, events=140),
        control_probe=probe("control", food=7, hunger=30, events=130),
    )
    assert report["attribution"]["eligible"] is False
    assert report["attribution"]["declared_difference"] is None
