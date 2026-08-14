from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any, Iterable

from pydantic import BaseModel, Field

from .behavioral_trajectory import BehavioralTrajectory, build_behavioral_trajectory
from .events import Event


PHENOTYPE_EVENT_TYPES: dict[str, tuple[str, ...]] = {
    "scarcity": (
        "scarcity.perceived",
        "scarcity.purchase",
    ),
    "rumor": (
        "rumor.generated",
        "rumor.spread",
        "rumor.rejected",
    ),
    "conflict": (
        "resource_conflict_propensity",
        "conflict.resolved",
        "decision.resource_conflict",
    ),
    "trade": (
        "trade.completed",
        "obligation.fulfilled",
        "obligation.defaulted",
    ),
    "social": (
        "social.helped",
        "relationship.changed",
        "relationship.updated",
    ),
}


class BehavioralPhenotype(BaseModel):
    name: str
    timeline_id: str
    selected_event_count: int
    event_counts: dict[str, int] = Field(default_factory=dict)
    participant_count: int = 0
    participant_event_counts: dict[str, int] = Field(default_factory=dict)
    first_tick: int | None = None
    last_tick: int | None = None
    active_tick_span: int = 0
    burst_tick_count: int = 0
    peak_events_per_tick: int = 0
    trajectory_fingerprint: str
    phenotype_fingerprint: str


def _canonical_hash(payload: Any) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _matches(name: str, event_type: str) -> bool:
    configured = PHENOTYPE_EVENT_TYPES.get(name)
    if configured is None:
        raise ValueError(f"unknown phenotype: {name}")
    if event_type in configured:
        return True
    if name == "conflict" and ("conflict" in event_type or "propensity" in event_type):
        return True
    if name == "trade" and (event_type.startswith("trade.") or event_type.startswith("obligation.")):
        return True
    if name == "social" and (event_type.startswith("social.") or event_type.startswith("relationship.")):
        return True
    return False


def build_behavioral_phenotype(
    events: Iterable[Event],
    *,
    timeline_id: str,
    name: str,
    actor_ids: Iterable[str] | None = None,
    from_tick: int | None = None,
    to_tick: int | None = None,
) -> BehavioralPhenotype:
    normalized = name.strip().lower()
    if normalized not in PHENOTYPE_EVENT_TYPES:
        raise ValueError(f"unknown phenotype: {name}")

    all_events = tuple(events)
    event_types = sorted({event.event_type for event in all_events if _matches(normalized, event.event_type)})
    trajectory: BehavioralTrajectory = build_behavioral_trajectory(
        all_events,
        timeline_id=timeline_id,
        event_types=event_types,
        actor_ids=actor_ids,
        from_tick=from_tick,
        to_tick=to_tick,
    )

    tick_counts: Counter[int] = Counter(item.tick for item in trajectory.event_sequence)
    first_tick = min(tick_counts) if tick_counts else None
    last_tick = max(tick_counts) if tick_counts else None
    active_tick_span = (last_tick - first_tick + 1) if first_tick is not None and last_tick is not None else 0
    peak_events = max(tick_counts.values()) if tick_counts else 0
    burst_ticks = sum(1 for count in tick_counts.values() if count >= 2)

    payload = {
        "name": normalized,
        "timeline_id": timeline_id,
        "selected_event_count": trajectory.selected_event_count,
        "event_counts": trajectory.event_counts,
        "participant_event_counts": trajectory.actor_event_counts,
        "first_tick": first_tick,
        "last_tick": last_tick,
        "active_tick_span": active_tick_span,
        "burst_tick_count": burst_ticks,
        "peak_events_per_tick": peak_events,
        "trajectory_fingerprint": trajectory.trajectory_fingerprint,
    }
    return BehavioralPhenotype(
        name=normalized,
        timeline_id=timeline_id,
        selected_event_count=trajectory.selected_event_count,
        event_counts=trajectory.event_counts,
        participant_count=len(trajectory.actor_event_counts),
        participant_event_counts=trajectory.actor_event_counts,
        first_tick=first_tick,
        last_tick=last_tick,
        active_tick_span=active_tick_span,
        burst_tick_count=burst_ticks,
        peak_events_per_tick=peak_events,
        trajectory_fingerprint=trajectory.trajectory_fingerprint,
        phenotype_fingerprint=_canonical_hash(payload),
    )


def phenotype_numeric_metrics(phenotype: BehavioralPhenotype) -> dict[str, float]:
    """Stable scalar metrics suitable for Phase J campaign behavioral aggregation."""
    metrics = {
        f"phenotype.{phenotype.name}.event_count": float(phenotype.selected_event_count),
        f"phenotype.{phenotype.name}.participant_count": float(phenotype.participant_count),
        f"phenotype.{phenotype.name}.active_tick_span": float(phenotype.active_tick_span),
        f"phenotype.{phenotype.name}.burst_tick_count": float(phenotype.burst_tick_count),
        f"phenotype.{phenotype.name}.peak_events_per_tick": float(phenotype.peak_events_per_tick),
    }
    if phenotype.first_tick is not None:
        metrics[f"phenotype.{phenotype.name}.first_tick"] = float(phenotype.first_tick)
    if phenotype.last_tick is not None:
        metrics[f"phenotype.{phenotype.name}.last_tick"] = float(phenotype.last_tick)
    return metrics
