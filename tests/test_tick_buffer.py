from pathlib import Path

import pytest

from worldos_core.events import NewEvent
from worldos_core.sqlite_store import SQLiteEventStore
from worldos_core.store import EventStoreError


def _event(tick: int, event_type: str) -> NewEvent:
    return NewEvent(
        tick=tick,
        phase="scheduler",
        event_type=event_type,
        payload={"tick": tick},
    )


def test_buffered_events_are_invisible_until_atomic_commit(tmp_path: Path) -> None:
    store = SQLiteEventStore(tmp_path / "world.db")
    store.begin_buffer("main")
    first = store.append_batch("main", [_event(1, "tick.started")], expected_sequence=0)
    second = store.append_batch("main", [_event(1, "tick.completed")], expected_sequence=1)

    assert store.read("main") == []
    assert first[0].sequence == 1
    assert second[0].sequence == 2

    store.commit_buffer("main")
    assert [event.event_type for event in store.read("main")] == [
        "tick.started",
        "tick.completed",
    ]
    store.close()


def test_buffer_rollback_leaves_no_partial_tick(tmp_path: Path) -> None:
    store = SQLiteEventStore(tmp_path / "world.db")
    store.begin_buffer("main")
    store.append_batch("main", [_event(1, "tick.started")], expected_sequence=0)
    store.rollback_buffer("main")

    assert store.read("main") == []
    store.close()


def test_buffer_commit_detects_out_of_band_writer(tmp_path: Path) -> None:
    path = tmp_path / "world.db"
    first = SQLiteEventStore(path)
    second = SQLiteEventStore(path)
    first.begin_buffer("main")
    first.append_batch("main", [_event(1, "tick.started")], expected_sequence=0)
    second.append_batch("main", [_event(0, "runner.resumed")], expected_sequence=0)

    with pytest.raises(EventStoreError, match="optimistic concurrency conflict"):
        first.commit_buffer("main")
    first.rollback_buffer("main")
    assert len(first.read("main")) == 1

    first.close()
    second.close()
