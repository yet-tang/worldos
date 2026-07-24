from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
import hashlib
import json
from typing import Iterable

from .events import Event, NewEvent
from .timeline import Timeline


class EventStoreError(RuntimeError):
    pass


class InMemoryEventStore:
    """Reference Event Store used to prove ordering, replay and branching semantics."""

    def __init__(self) -> None:
        self._timelines: dict[str, Timeline] = {"main": Timeline(timeline_id="main")}
        self._events: dict[str, list[Event]] = defaultdict(list)

    def create_timeline(self, timeline_id: str, *, parent_timeline_id: str = "main", parent_through_sequence: int | None = None) -> Timeline:
        if timeline_id in self._timelines:
            raise EventStoreError(f"timeline already exists: {timeline_id}")
        if parent_timeline_id not in self._timelines:
            raise EventStoreError(f"unknown parent timeline: {parent_timeline_id}")
        parent_events = self.read(parent_timeline_id)
        cutoff = len(parent_events) if parent_through_sequence is None else parent_through_sequence
        if cutoff < 0 or cutoff > len(parent_events):
            raise EventStoreError("parent cutoff is outside visible history")
        timeline = Timeline(timeline_id=timeline_id, parent_timeline_id=parent_timeline_id, parent_through_sequence=cutoff)
        self._timelines[timeline_id] = timeline
        return timeline

    def append_batch(self, timeline_id: str, events: Iterable[NewEvent], *, expected_sequence: int | None = None) -> list[Event]:
        if timeline_id not in self._timelines:
            raise EventStoreError(f"unknown timeline: {timeline_id}")
        new_events = list(events)
        visible_count = len(self.read(timeline_id))
        if expected_sequence is not None and expected_sequence != visible_count:
            raise EventStoreError(f"optimistic concurrency conflict: expected {expected_sequence}, got {visible_count}")
        committed: list[Event] = []
        for offset, candidate in enumerate(new_events, start=1):
            sequence = visible_count + offset
            event_id = self._event_id(timeline_id, sequence, candidate)
            committed.append(Event(**candidate.model_dump(), event_id=event_id, timeline_id=timeline_id, sequence=sequence))
        self._events[timeline_id].extend(deepcopy(committed))
        return committed

    def read(self, timeline_id: str, through_sequence: int | None = None) -> list[Event]:
        if timeline_id not in self._timelines:
            raise EventStoreError(f"unknown timeline: {timeline_id}")
        timeline = self._timelines[timeline_id]
        inherited: list[Event] = []
        if timeline.parent_timeline_id is not None:
            inherited = self.read(timeline.parent_timeline_id, timeline.parent_through_sequence)
        combined = [*inherited, *self._events[timeline_id]]
        if through_sequence is not None:
            combined = combined[:through_sequence]
        return deepcopy(combined)

    def timeline(self, timeline_id: str) -> Timeline:
        try:
            return self._timelines[timeline_id].model_copy(deep=True)
        except KeyError as exc:
            raise EventStoreError(f"unknown timeline: {timeline_id}") from exc

    @staticmethod
    def _event_id(timeline_id: str, sequence: int, event: NewEvent) -> str:
        canonical = json.dumps(event.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(f"{timeline_id}:{sequence}:{canonical}".encode()).hexdigest()
        return f"evt_{digest[:24]}"
