from worldos_core.behavioral_phenotype import (
    build_behavioral_phenotype,
    compare_behavioral_phenotypes,
    phenotype_comparison_numeric_metrics,
    phenotype_numeric_metrics,
)
from worldos_core.events import Event


def _event(sequence: int, tick: int, event_type: str, actor_id: str | None = None, subject_ids=()):
    return Event(tick=tick, phase="social", event_type=event_type, actor_id=actor_id, subject_ids=tuple(subject_ids), event_id=f"event-{sequence}", timeline_id="main", sequence=sequence)


def test_scarcity_phenotype_summarizes_timing_participation_and_bursts():
    events = [_event(1, 5, "scarcity.perceived", "a"), _event(2, 5, "scarcity.perceived", "b"), _event(3, 7, "scarcity.purchase", "a", ("c",)), _event(4, 8, "rumor.generated", "b")]
    phenotype = build_behavioral_phenotype(events, timeline_id="main", name="scarcity")
    assert phenotype.selected_event_count == 3
    assert phenotype.event_counts == {"scarcity.perceived": 2, "scarcity.purchase": 1}
    assert phenotype.first_tick == 5
    assert phenotype.last_tick == 7
    assert phenotype.active_tick_span == 3
    assert phenotype.burst_tick_count == 1
    assert phenotype.peak_events_per_tick == 2
    assert phenotype.participant_count == 3
    assert phenotype.phenotype_fingerprint


def test_conflict_phenotype_accepts_existing_conflict_event_variants():
    events = [_event(1, 10, "resource_conflict_propensity", "a", ("b",)), _event(2, 11, "decision.resource_conflict", "a", ("b",)), _event(3, 12, "conflict.resolved", "a", ("b",)), _event(4, 13, "trade.completed", "a", ("b",))]
    phenotype = build_behavioral_phenotype(events, timeline_id="main", name="conflict")
    assert phenotype.selected_event_count == 3
    assert phenotype.first_tick == 10
    assert phenotype.last_tick == 12


def test_phenotype_numeric_metrics_are_campaign_ready_and_deterministic():
    events = [_event(1, 2, "rumor.generated", "a"), _event(2, 3, "rumor.spread", "a", ("b",)), _event(3, 3, "rumor.rejected", "b", ("a",))]
    first = build_behavioral_phenotype(events, timeline_id="main", name="rumor")
    second = build_behavioral_phenotype(list(reversed(events)), timeline_id="main", name="rumor")
    assert first == second
    metrics = phenotype_numeric_metrics(first)
    assert metrics["phenotype.rumor.event_count"] == 3.0
    assert metrics["phenotype.rumor.first_tick"] == 2.0
    assert metrics["phenotype.rumor.last_tick"] == 3.0
    assert metrics["phenotype.rumor.burst_tick_count"] == 1.0


def test_actor_filter_keeps_events_when_actor_is_subject():
    events = [_event(1, 1, "trade.completed", "seller", ("buyer",)), _event(2, 2, "trade.completed", "other", ("third",))]
    phenotype = build_behavioral_phenotype(events, timeline_id="main", name="trade", actor_ids=["buyer"])
    assert phenotype.selected_event_count == 1
    assert phenotype.participant_event_counts["buyer"] == 1


def test_compare_phenotypes_exposes_timing_density_and_participant_deltas():
    treatment = build_behavioral_phenotype([
        _event(1, 4, "scarcity.perceived", "a"),
        _event(2, 5, "scarcity.purchase", "a", ("b",)),
        _event(3, 5, "scarcity.purchase", "c", ("b",)),
    ], timeline_id="treatment", name="scarcity")
    control = build_behavioral_phenotype([
        _event(1, 7, "scarcity.perceived", "a"),
        _event(2, 9, "scarcity.purchase", "a", ("b",)),
    ], timeline_id="control", name="scarcity")
    comparison = compare_behavioral_phenotypes(treatment, control)
    assert comparison.identical is False
    assert comparison.event_count_delta == 1
    assert comparison.first_tick_delta == -3
    assert comparison.last_tick_delta == -4
    assert comparison.event_type_deltas["scarcity.purchase"] == 1
    assert comparison.participant_event_deltas["c"] == 1
    metrics = phenotype_comparison_numeric_metrics(comparison)
    assert metrics["phenotype.scarcity.event_count_delta"] == 1.0
    assert metrics["phenotype.scarcity.first_tick_delta"] == -3.0


def test_compare_phenotypes_rejects_mismatched_domains():
    scarcity = build_behavioral_phenotype([], timeline_id="t", name="scarcity")
    rumor = build_behavioral_phenotype([], timeline_id="c", name="rumor")
    import pytest
    with pytest.raises(ValueError, match="phenotype names must match"):
        compare_behavioral_phenotypes(scarcity, rumor)
