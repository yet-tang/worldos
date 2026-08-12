from __future__ import annotations

from typing import Any, Protocol

from .timeline import Timeline


class TimelineStore(Protocol):
    def timeline(self, timeline_id: str) -> Timeline: ...
    def read(self, timeline_id: str, through_sequence: int | None = None) -> list[Any]: ...


def timeline_lineage(store: TimelineStore, timeline_id: str) -> dict[str, Any]:
    """Return root-to-leaf lineage for a timeline without mutating the store.

    Each node records the parent cutoff that became immutable ancestry for the child.
    This makes nested experimental branches auditable and lets callers prove that a
    second-generation branch inherited the exact history of its immediate parent.
    """

    chain: list[dict[str, Any]] = []
    seen: set[str] = set()
    current_id: str | None = timeline_id

    while current_id is not None:
        if current_id in seen:
            raise RuntimeError(f"timeline lineage cycle detected at {current_id}")
        seen.add(current_id)
        timeline = store.timeline(current_id)
        chain.append(
            {
                "timeline_id": timeline.timeline_id,
                "parent_timeline_id": timeline.parent_timeline_id,
                "parent_through_sequence": timeline.parent_through_sequence,
                "visible_event_count": len(store.read(current_id)),
            }
        )
        current_id = timeline.parent_timeline_id

    chain.reverse()
    return {
        "timeline_id": timeline_id,
        "depth": max(0, len(chain) - 1),
        "root_timeline_id": chain[0]["timeline_id"],
        "lineage": chain,
    }
