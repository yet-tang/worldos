from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


StimulusKind = Literal[
    "resource_shock",
    "environment_event",
    "spread_information",
    "social_incident",
    "policy_change",
]


class SemanticStimulus(BaseModel):
    """Typed, replay-safe external intervention understood by WorldOS experiments."""

    kind: StimulusKind
    magnitude: float = Field(default=0.0, ge=-1.0, le=1.0)
    duration_ticks: int = Field(default=1, ge=1, le=10000)
    resource: str | None = None
    message: str | None = None
    location_id: str | None = None
    actor_ids: tuple[str, ...] = ()
    policy: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_kind_fields(self) -> "SemanticStimulus":
        if self.kind == "resource_shock" and not self.resource:
            raise ValueError("resource_shock requires resource")
        if self.kind == "spread_information" and not self.message:
            raise ValueError("spread_information requires message")
        if self.kind == "policy_change" and not self.policy:
            raise ValueError("policy_change requires policy")
        return self

    def event_payload(self) -> dict[str, Any]:
        return {
            "stimulus_kind": self.kind,
            "magnitude": self.magnitude,
            "duration_ticks": self.duration_ticks,
            "resource": self.resource,
            "message": self.message,
            "location_id": self.location_id,
            "actor_ids": list(self.actor_ids),
            "policy": self.policy,
            "metadata": self.metadata,
        }


def semantic_event(*, tick: int, stimulus: SemanticStimulus, experiment_id: str | None = None) -> dict[str, Any]:
    metadata: dict[str, Any] = {"semantic_stimulus": True}
    if experiment_id:
        metadata["experiment_id"] = experiment_id
    return {
        "tick": tick,
        "phase": "external",
        "event_type": f"world.stimulus.{stimulus.kind}",
        "payload": stimulus.event_payload(),
        "metadata": metadata,
    }
