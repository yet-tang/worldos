from __future__ import annotations

from pydantic import BaseModel


class Timeline(BaseModel):
    timeline_id: str
    parent_timeline_id: str | None = None
    parent_through_sequence: int = 0
