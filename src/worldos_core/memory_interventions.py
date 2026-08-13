from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Literal

from pydantic import BaseModel, Field

from .events import Event, NewEvent


MemoryInterventionMode = Literal["retain", "suppress", "reinforce", "replace"]


class MemorySelector(BaseModel):
    actor_ids: tuple[str, ...] = ()
    experience_types: tuple[str, ...] = ()
    memory_ids: tuple[str, ...] = ()


class MemoryIntervention(BaseModel):
    mode: MemoryInterventionMode
    selector: MemorySelector = Field(default_factory=MemorySelector)
    multiplier: float = 1.0
    replacement: dict[str, Any] | None = None
    reason: str = "experimental treatment"


@dataclass(frozen=True)
class MemoryTreatmentEffect:
    suppressed: bool = False
    multiplier: float = 1.0
    replacement: dict[str, Any] | None = None
    intervention_event_ids: tuple[str, ...] = ()


def build_memory_intervention_event(
    intervention: MemoryIntervention,
    *,
    tick: int,
    actor_id: str | None = None,
) -> NewEvent:
    if intervention.mode == "reinforce" and intervention.multiplier <= 0:
        raise ValueError("reinforcement multiplier must be positive")
    if intervention.mode == "replace" and not isinstance(intervention.replacement, dict):
        raise ValueError("replace intervention requires replacement memory content")
    return NewEvent(
        tick=tick,
        phase="experiment",
        event_type="experiment.memory_intervention",
        actor_id=actor_id,
        subject_ids=((actor_id,) if actor_id else ()),
        payload=intervention.model_dump(mode="json"),
    )


def _selector_matches(
    selector: MemorySelector,
    *,
    owner_id: str,
    memory_id: str,
    experience_type: str,
) -> bool:
    if selector.actor_ids and owner_id not in selector.actor_ids:
        return False
    if selector.memory_ids and memory_id not in selector.memory_ids:
        return False
    if selector.experience_types and experience_type not in selector.experience_types:
        return False
    return True


def treatment_for_memory(
    history: Iterable[Event],
    *,
    owner_id: str,
    memory_id: str,
    experience_type: str,
) -> MemoryTreatmentEffect:
    """Resolve branch-local intervention events into an auditable memory treatment.

    Historical memory events stay immutable. Later intervention events alter only their
    effective contribution to adaptive strategy on the current timeline.
    """

    suppressed = False
    multiplier = 1.0
    replacement: dict[str, Any] | None = None
    applied: list[str] = []
    for event in history:
        if event.event_type != "experiment.memory_intervention":
            continue
        try:
            intervention = MemoryIntervention.model_validate(event.payload)
        except Exception:
            continue
        if not _selector_matches(
            intervention.selector,
            owner_id=owner_id,
            memory_id=memory_id,
            experience_type=experience_type,
        ):
            continue
        applied.append(event.event_id)
        if intervention.mode == "retain":
            suppressed = False
            multiplier = 1.0
            replacement = None
        elif intervention.mode == "suppress":
            suppressed = True
        elif intervention.mode == "reinforce":
            multiplier *= float(intervention.multiplier)
        elif intervention.mode == "replace":
            suppressed = True
            replacement = dict(intervention.replacement or {})
    return MemoryTreatmentEffect(
        suppressed=suppressed,
        multiplier=round(multiplier, 6),
        replacement=replacement,
        intervention_event_ids=tuple(applied),
    )
