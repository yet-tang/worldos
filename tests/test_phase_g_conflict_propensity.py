from worldos_core.conflict_propensity import conflict_propensity


def evaluate(**overrides):
    values = {
        "pressure": 90,
        "hunger": 75,
        "shortage": 4,
        "scarcity_ticks": 6,
        "rumor_pressure": 2,
        "relationship": -20,
        "own_food": 1,
        "target_food": 8,
        "conflict_caution": 0,
        "alternative_sellers": 0,
        "target_avoided": True,
    }
    values.update(overrides)
    return conflict_propensity(**values)


def test_severe_scarcity_with_grievance_can_trigger_conflict():
    result = evaluate()
    assert result["triggered"] is True
    assert result["score"] >= result["trigger_score"]
    assert result["drivers"]["pressure"] > 0
    assert result["drivers"]["relative_inequality"] > 0
    assert result["drivers"]["grievance"] > 0


def test_adaptive_caution_and_market_alternatives_are_real_brakes():
    baseline = evaluate(target_avoided=False, relationship=0)
    buffered = evaluate(
        target_avoided=False,
        relationship=20,
        conflict_caution=25,
        alternative_sellers=3,
    )
    assert buffered["score"] < baseline["score"]
    assert buffered["brakes"]["adaptive_caution"] == 25
    assert buffered["brakes"]["market_alternatives"] == 18
    assert buffered["brakes"]["positive_relationship"] == 4


def test_same_inputs_are_exactly_deterministic():
    first = evaluate()
    second = evaluate()
    assert first == second


def test_caution_can_prevent_escalation_even_under_same_physical_scarcity():
    naive = evaluate(
        pressure=82,
        hunger=60,
        shortage=3,
        scarcity_ticks=4,
        rumor_pressure=1,
        relationship=-5,
        own_food=1,
        target_food=6,
        target_avoided=False,
        conflict_caution=0,
    )
    experienced = evaluate(
        pressure=82,
        hunger=60,
        shortage=3,
        scarcity_ticks=4,
        rumor_pressure=1,
        relationship=-5,
        own_food=1,
        target_food=6,
        target_avoided=False,
        conflict_caution=25,
    )
    assert experienced["score"] == naive["score"] - 25
    assert experienced["score"] < naive["score"]


def test_propensity_payload_is_explainable_and_auditable():
    result = evaluate()
    assert set(result) == {"score", "trigger_score", "triggered", "drivers", "brakes", "inputs"}
    assert result["inputs"]["pressure"] == 90
    assert "scarcity_duration" in result["drivers"]
    assert "adaptive_caution" in result["brakes"]
