from __future__ import annotations

import pytest
from pydantic import ValidationError

from worldos_core.experiments import compare_probes
from worldos_core.semantic_stimulus import SemanticStimulus, semantic_event


def test_resource_shock_requires_resource_and_builds_extension_event() -> None:
    stimulus = SemanticStimulus(kind="resource_shock", resource="food", magnitude=-0.4, duration_ticks=30)
    event = semantic_event(tick=130, stimulus=stimulus, experiment_id="food-crisis-1")
    assert event["event_type"] == "world.stimulus.resource_shock"
    assert event["payload"]["resource"] == "food"
    assert event["payload"]["magnitude"] == -0.4
    assert event["metadata"]["experiment_id"] == "food-crisis-1"


def test_semantic_stimulus_rejects_incomplete_contracts() -> None:
    with pytest.raises(ValidationError):
        SemanticStimulus(kind="resource_shock", magnitude=-0.4)
    with pytest.raises(ValidationError):
        SemanticStimulus(kind="spread_information")
    with pytest.raises(ValidationError):
        SemanticStimulus(kind="policy_change")


def test_compare_probes_reports_actor_event_and_metric_deltas() -> None:
    control = {
        "snapshot": {"timeline_id": "main", "current_tick": 10, "event_count": 100, "world_hash": "a"},
        "actors": [{"actor_id": "a1", "health": {"current": 100}, "needs": {"hunger": 20, "fatigue": 10}, "wallet": 5, "inventory": {"food": 10}}],
        "recent_events": [{"event_type": "resource.produced"}],
    }
    experiment = {
        "snapshot": {"timeline_id": "food-crisis", "current_tick": 20, "event_count": 160, "world_hash": "b"},
        "actors": [{"actor_id": "a1", "health": {"current": 90}, "needs": {"hunger": 35, "fatigue": 12}, "wallet": 4, "inventory": {"food": 4}}],
        "recent_events": [{"event_type": "conflict.resolved"}],
    }
    result = compare_probes(control, experiment)
    assert result["control"]["timeline"] == "main"
    assert result["experiment"]["timeline"] == "food-crisis"
    assert result["delta"]["tick"] == 10
    assert result["delta"]["events"] == 60
    assert result["delta"]["actor_change_count"] == 1
    assert result["delta"]["metrics"]["average_hunger"] == 15.0
    assert result["delta"]["metrics"]["average_health"] == -10.0
    assert result["delta"]["metrics"]["inventory_totals"]["food"] == -6.0
