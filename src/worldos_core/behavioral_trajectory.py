from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any, Iterable

from pydantic import BaseModel, Field

from .events import Event


class TrajectoryMilestone(BaseModel):
    event_type: str
    tick: int
    sequence: int
    actor_id: str | None = None
    subject_ids: tuple[str, ...] = ()


class BehavioralTrajectory(BaseModel):
    timeline_id: str
    from_tick: int | None = None
    to_tick: int | None = None
    selected_event_count: int
    event_counts: dict[str, int] = Field(default_factory=dict)
    actor_event_counts: dict[str, int] = Field(default_factory=dict)
    first_occurrence: dict[str, TrajectoryMilestone] = Field(default_factory=dict)
    last_occurrence: dict[str, TrajectoryMilestone] = Field(default_factory=dict)
    event_sequence: tuple[TrajectoryMilestone, ...] = ()
    trajectory_fingerprint: str


class BehavioralTrajectoryComparison(BaseModel):
    treatment_timeline: str
    control_timeline: str
    treatment_fingerprint: str
    control_fingerprint: str
    identical: bool
    first_divergence_index: int | None = None
    first_divergence_tick: int | None = None
    event_count_delta: dict[str, int] = Field(default_factory=dict)
    first_occurrence_tick_delta: dict[str, int | None] = Field(default_factory=dict)
    actor_event_count_delta: dict[str, int] = Field(default_factory=dict)
    comparison_fingerprint: str


def _canonical_hash(payload: Any) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _milestone(event: Event) -> TrajectoryMilestone:
    return TrajectoryMilestone(
        event_type=event.event_type,
        tick=event.tick,
        sequence=event.sequence,
        actor_id=event.actor_id,
        subject_ids=tuple(event.subject_ids),
    )


def _selected(
    event: Event,
    *,
    event_types: set[str] | None,
    actor_ids: set[str] | None,
    from_tick: int | None,
    to_tick: int | None,
) -> bool:
    if from_tick is not None and event.tick < from_tick:
        return False
    if to_tick is not None and event.tick > to_tick:
        return False
    if event_types is not None and event.event_type not in event_types:
        return False
    if actor_ids is not None:
        participants = ({event.actor_id} if event.actor_id else set()) | set(event.subject_ids)
        if not participants.intersection(actor_ids):
            return False
    return True


def build_behavioral_trajectory(
    events: Iterable[Event],
    *,
    timeline_id: str,
    event_types: Iterable[str] | None = None,
    actor_ids: Iterable[str] | None = None,
    from_tick: int | None = None,
    to_tick: int | None = None,
    max_sequence_events: int = 5000,
) -> BehavioralTrajectory:
    if max_sequence_events < 1:
        raise ValueError("max_sequence_events must be positive")
    type_filter = {str(item) for item in event_types} if event_types is not None else None
    actor_filter = {str(item) for item in actor_ids} if actor_ids is not None else None

    selected = [
        event
        for event in events
        if _selected(
            event,
            event_types=type_filter,
            actor_ids=actor_filter,
            from_tick=from_tick,
            to_tick=to_tick,
        )
    ]
    selected.sort(key=lambda event: (event.sequence, event.event_id))

    event_counts = Counter(event.event_type for event in selected)
    actor_counts: Counter[str] = Counter()
    first: dict[str, TrajectoryMilestone] = {}
    last: dict[str, TrajectoryMilestone] = {}
    milestones: list[TrajectoryMilestone] = []

    for event in selected:
        point = _milestone(event)
        first.setdefault(event.event_type, point)
        last[event.event_type] = point
        if event.actor_id:
            actor_counts[event.actor_id] += 1
        for subject_id in event.subject_ids:
            actor_counts[subject_id] += 1
        if len(milestones) < max_sequence_events:
            milestones.append(point)

    fingerprint_payload = {
        "timeline_id": timeline_id,
        "from_tick": from_tick,
        "to_tick": to_tick,
        "event_counts": dict(sorted(event_counts.items())),
        "actor_event_counts": dict(sorted(actor_counts.items())),
        "event_sequence": [item.model_dump(mode="json") for item in milestones],
        "selected_event_count": len(selected),
    }
    return BehavioralTrajectory(
        timeline_id=timeline_id,
        from_tick=from_tick,
        to_tick=to_tick,
        selected_event_count=len(selected),
        event_counts=dict(sorted(event_counts.items())),
        actor_event_counts=dict(sorted(actor_counts.items())),
        first_occurrence=first,
        last_occurrence=last,
        event_sequence=tuple(milestones),
        trajectory_fingerprint=_canonical_hash(fingerprint_payload),
    )


def compare_behavioral_trajectories(
    treatment: BehavioralTrajectory,
    control: BehavioralTrajectory,
) -> BehavioralTrajectoryComparison:
    treatment_seq = treatment.event_sequence
    control_seq = control.event_sequence
    common_length = min(len(treatment_seq), len(control_seq))
    divergence_index: int | None = None
    divergence_tick: int | None = None
    for index in range(common_length):
        left = treatment_seq[index]
        right = control_seq[index]
        left_signature = (left.event_type, left.tick, left.actor_id, left.subject_ids)
        right_signature = (right.event_type, right.tick, right.actor_id, right.subject_ids)
        if left_signature != right_signature:
            divergence_index = index
            divergence_tick = min(left.tick, right.tick)
            break
    if divergence_index is None and len(treatment_seq) != len(control_seq):
        divergence_index = common_length
        remaining = treatment_seq[common_length:] or control_seq[common_length:]
        divergence_tick = remaining[0].tick if remaining else None

    event_names = sorted(set(treatment.event_counts) | set(control.event_counts))
    event_delta = {
        name: treatment.event_counts.get(name, 0) - control.event_counts.get(name, 0)
        for name in event_names
    }
    actors = sorted(set(treatment.actor_event_counts) | set(control.actor_event_counts))
    actor_delta = {
        actor: treatment.actor_event_counts.get(actor, 0) - control.actor_event_counts.get(actor, 0)
        for actor in actors
    }
    first_names = sorted(set(treatment.first_occurrence) | set(control.first_occurrence))
    first_delta: dict[str, int | None] = {}
    for name in first_names:
        left = treatment.first_occurrence.get(name)
        right = control.first_occurrence.get(name)
        first_delta[name] = left.tick - right.tick if left is not None and right is not None else None

    identical = treatment.trajectory_fingerprint == control.trajectory_fingerprint
    payload = {
        "treatment_fingerprint": treatment.trajectory_fingerprint,
        "control_fingerprint": control.trajectory_fingerprint,
        "first_divergence_index": divergence_index,
        "first_divergence_tick": divergence_tick,
        "event_count_delta": event_delta,
        "first_occurrence_tick_delta": first_delta,
        "actor_event_count_delta": actor_delta,
    }
    return BehavioralTrajectoryComparison(
        treatment_timeline=treatment.timeline_id,
        control_timeline=control.timeline_id,
        treatment_fingerprint=treatment.trajectory_fingerprint,
        control_fingerprint=control.trajectory_fingerprint,
        identical=identical,
        first_divergence_index=divergence_index,
        first_divergence_tick=divergence_tick,
        event_count_delta=event_delta,
        first_occurrence_tick_delta=first_delta,
        actor_event_count_delta=actor_delta,
        comparison_fingerprint=_canonical_hash(payload),
    )
