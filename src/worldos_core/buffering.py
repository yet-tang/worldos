from __future__ import annotations

from typing import Protocol


class TickBufferedStore(Protocol):
    """Optional Event Store capability used to atomically commit one complete tick."""

    def begin_buffer(self, timeline_id: str) -> None: ...

    def commit_buffer(self, timeline_id: str) -> None: ...

    def rollback_buffer(self, timeline_id: str) -> None: ...
