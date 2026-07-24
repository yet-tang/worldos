from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class NewEvent(BaseModel):
    """An event before store-assigned identity and sequence."""

    tick: int
    phase: str
    event_type: str
    schema_version: int = 1
    actor_id: str | None = None
    subject_ids: tuple[str, ...] = ()
    caused_by: tuple[str, ...] = ()
    correlation_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Event(NewEvent):
    """Immutable event envelope committed to one timeline."""

    event_id: str
    timeline_id: str
    sequence: int
