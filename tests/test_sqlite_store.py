from __future__ import annotations

import sqlite3

import pytest

from worldos_core import EventStoreError, NewEvent, SQLiteEventStore


def event(name: str, tick: int = 1) -> NewEvent:
    return NewEvent(tick=tick, phase="test", event_type=name, payload={"name": name})


def test_reopen_preserves_events_and_deterministic_ids(tmp_path) -> None:
    path = tmp_path / "world.db"
    with SQLiteEventStore(path) as store:
        committed = store.append_batch("main", [event("world.started")], expected_sequence=0)
        event_id = committed[0].event_id

    with SQLiteEventStore(path) as reopened:
        events = reopened.read("main")
        assert [item.event_type for item in events] == ["world.started"]
        assert events[0].event_id == event_id
        assert reopened.integrity_check()


def test_persistent_branch_inherits_cutoff_and_appends_locally(tmp_path) -> None:
    path = tmp_path / "world.db"
    with SQLiteEventStore(path) as store:
        store.append_batch("main", [event("one"), event("two")])
        store.create_timeline("alternate", parent_through_sequence=1)
        branch_event = store.append_batch(
            "alternate", [event("alternate.two")], expected_sequence=1
        )[0]
        assert branch_event.sequence == 2

    with SQLiteEventStore(path) as reopened:
        assert [item.event_type for item in reopened.read("main")] == ["one", "two"]
        assert [item.event_type for item in reopened.read("alternate")] == [
            "one",
            "alternate.two",
        ]
        assert reopened.timeline("alternate").parent_through_sequence == 1


def test_optimistic_conflict_rolls_back_entire_batch(tmp_path) -> None:
    path = tmp_path / "world.db"
    with SQLiteEventStore(path) as store:
        store.append_batch("main", [event("one")])
        with pytest.raises(EventStoreError, match="optimistic concurrency conflict"):
            store.append_batch("main", [event("two"), event("three")], expected_sequence=0)
        assert [item.event_type for item in store.read("main")] == ["one"]


def test_snapshots_are_hashed_persisted_and_bounded_by_history(tmp_path) -> None:
    path = tmp_path / "world.db"
    with SQLiteEventStore(path) as store:
        store.append_batch("main", [event("one"), event("two")])
        first = store.save_snapshot("main", 1, "world", {"entities": {"a": 1}})
        second = store.save_snapshot("main", 2, "world", {"entities": {"a": 2}})
        assert first.state_hash != second.state_hash
        assert store.latest_snapshot("main", "world", through_sequence=1) == first

    with SQLiteEventStore(path) as reopened:
        assert reopened.latest_snapshot("main", "world") == second
        with pytest.raises(EventStoreError, match="outside visible history"):
            reopened.save_snapshot("main", 3, "world", {})


def test_uncommitted_sqlite_transaction_is_not_visible_after_recovery(tmp_path) -> None:
    path = tmp_path / "world.db"
    store = SQLiteEventStore(path)
    store.append_batch("main", [event("committed")])
    store.close()

    connection = sqlite3.connect(path)
    connection.execute("BEGIN IMMEDIATE")
    connection.execute(
        "INSERT INTO events(timeline_id, sequence, event_id, document) VALUES (?, ?, ?, ?)",
        (
            "main",
            2,
            "evt_interrupted",
            '{"tick":1,"phase":"test","event_type":"interrupted",'
            '"schema_version":1,"actor_id":null,"subject_ids":[],"caused_by":[],'
            '"correlation_id":null,"payload":{},"metadata":{},'
            '"event_id":"evt_interrupted","timeline_id":"main","sequence":2}',
        ),
    )
    connection.close()

    with SQLiteEventStore(path) as recovered:
        assert [item.event_type for item in recovered.read("main")] == ["committed"]
        assert recovered.integrity_check()
