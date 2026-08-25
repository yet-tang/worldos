from worldos_core.behavioral_trajectory import build_behavioral_trajectory, compare_behavioral_trajectories
from worldos_core.events import Event


def _event(sequence: int, tick: int, event_type: str, actor_id: str | None = None, subjects: tuple[str, ...] = ()) -> Event:
    return Event(
        event_id=f"e-{sequence}",
        timeline_id="t",
        sequence=sequence,
        tick=tick,
        phase="social",
        event_type=event_type,
        actor_id=actor_id,
        subject_ids=subjects,
    )


def test_build_behavioral_trajectory_tracks_counts_first_last_and_actor_participation():
    events = [
        _event(1, 5, "scarcity.perceived", "a"),
        _event(2, 6, "scarcity.purchase", "a", ("b",)),
        _event(3, 8, "rumor.spread", "b", ("c",)),
        _event(4, 10, "scarcity.purchase", "c", ("b",)),
    ]
    trajectory = build_behavioral_trajectory(events, timeline_id="t")
    assert trajectory.selected_event_count == 4
    assert trajectory.event_counts == {
        "rumor.spread": 1,
        "scarcity.perceived": 1,
        "scarcity.purchase": 2,
    }
    assert trajectory.first_occurrence["scarcity.purchase"].tick == 6
    assert trajectory.last_occurrence["scarcity.purchase"].tick == 10
    assert trajectory.actor_event_counts["a"] == 2
    assert trajectory.actor_event_counts["b"] == 3
    assert trajectory.actor_event_counts["c"] == 2
    assert trajectory.trajectory_fingerprint


def test_build_behavioral_trajectory_filters_by_tick_type_and_actor():
    events = [
        _event(1, 1, "noise", "z"),
        _event(2, 5, "conflict.resolved", "a", ("b",)),
        _event(3, 7, "conflict.resolved", "c", ("d",)),
        _event(4, 9, "scarcity.purchase", "a", ("d",)),
    ]
    trajectory = build_behavioral_trajectory(
        events,
        timeline_id="t",
        event_types=["conflict.resolved", "scarcity.purchase"],
        actor_ids=["a"],
        from_tick=5,
        to_tick=8,
    )
    assert trajectory.selected_event_count == 1
    assert trajectory.event_sequence[0].event_type == "conflict.resolved"
    assert trajectory.event_sequence[0].actor_id == "a"


def test_compare_behavioral_trajectories_finds_first_divergence_and_deltas():
    common = [
        _event(1, 5, "scarcity.perceived", "a"),
        _event(2, 6, "scarcity.purchase", "a", ("b",)),
    ]
    treatment = build_behavioral_trajectory(
        common + [_event(3, 9, "conflict.resolved", "a", ("b",))],
        timeline_id="treatment",
    )
    control = build_behavioral_trajectory(
        common + [_event(3, 11, "rumor.spread", "a", ("c",)), _event(4, 12, "conflict.resolved", "a", ("c",))],
        timeline_id="control",
    )
    comparison = compare_behavioral_trajectories(treatment, control)
    assert comparison.identical is False
    assert comparison.first_divergence_index == 2
    assert comparison.first_divergence_tick == 9
    assert comparison.event_count_delta["conflict.resolved"] == 0
    assert comparison.event_count_delta["rumor.spread"] == -1
    assert comparison.first_occurrence_tick_delta["conflict.resolved"] == -3
    assert comparison.actor_event_count_delta["c"] == -2
    assert comparison.comparison_fingerprint


def test_trajectory_is_deterministic_for_equivalent_event_input_order():
    events = [
        _event(2, 6, "b", "x"),
        _event(1, 5, "a", "x"),
    ]
    first = build_behavioral_trajectory(events, timeline_id="t")
    second = build_behavioral_trajectory(list(reversed(events)), timeline_id="t")
    assert first == second
