from copy import deepcopy

from worldos_core.modules import ModuleContext
from worldos_core.survival import SurvivalEconomyModule
from worldos_core.world import WorldProjection


def context():
    return ModuleContext(timeline_id="experiment", tick=20, world=WorldProjection(flags={"seed": "phase-g"}), history=())


def base_staged():
    return {
        "人物-001": {
            "position": {"location_id": "集市"},
            "inventory": {"food": 1},
            "wallet": 2,
            "needs": {"hunger": 80},
            "food_security": {"pressure": 95, "shortage": 5, "rumor_pressure": 2, "scarcity_ticks": 6, "target_reserve": 8},
            "relationships": {"人物-002": -30},
            "adaptive_strategy": {"conflict_caution": 0, "avoided_partners": ["人物-002"]},
        },
        "人物-002": {
            "position": {"location_id": "集市"},
            "inventory": {"food": 9},
            "wallet": 2,
            "needs": {"hunger": 20},
            "food_security": {"pressure": 0, "shortage": 0, "rumor_pressure": 0, "scarcity_ticks": 0, "target_reserve": 2},
            "relationships": {"人物-001": -30},
            "adaptive_strategy": {},
        },
    }


def test_runtime_emits_propensity_evidence_before_escalation():
    staged = base_staged()
    audit = []
    SurvivalEconomyModule()._scarcity_conflicts(context(), staged, audit)

    assert staged["人物-001"]["conflict"]["target_id"] == "人物-002"
    evaluations = [event for event in audit if event.payload.get("decision") == "resource_conflict_propensity"]
    escalations = [event for event in audit if event.payload.get("decision") == "resource_conflict"]
    assert len(evaluations) == 1
    assert len(escalations) == 1
    evidence = evaluations[0].payload["because"]
    assert evidence["triggered"] is True
    assert evidence["drivers"]["grievance"] > 0
    assert evidence["drivers"]["relative_inequality"] > 0


def test_learned_caution_and_trade_option_can_prevent_same_crisis_from_escalating():
    staged = base_staged()
    staged["人物-001"]["adaptive_strategy"] = {"conflict_caution": 25, "avoided_partners": []}
    staged["人物-001"]["relationships"]["人物-002"] = 20
    staged["人物-003"] = {
        "position": {"location_id": "集市"},
        "inventory": {"food": 7},
        "wallet": 1,
        "needs": {"hunger": 20},
        "food_security": {"pressure": 0, "shortage": 0, "rumor_pressure": 0, "scarcity_ticks": 0, "target_reserve": 2},
        "relationships": {},
        "adaptive_strategy": {},
    }

    audit = []
    SurvivalEconomyModule()._scarcity_conflicts(context(), staged, audit)

    assert "conflict" not in staged["人物-001"]
    evaluations = [event for event in audit if event.payload.get("decision") == "resource_conflict_propensity"]
    assert len(evaluations) == 1
    evidence = evaluations[0].payload["because"]
    assert evidence["triggered"] is False
    assert evidence["brakes"]["adaptive_caution"] == 25
    assert evidence["brakes"]["market_alternatives"] >= 6
