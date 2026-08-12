from worldos_core.events import NewEvent
from worldos_core.sqlite_store import SQLiteEventStore
from worldos_core.timeline_lineage import timeline_lineage


def test_branch_of_branch_inherits_immediate_parent_history(tmp_path) -> None:
    path = tmp_path / "world.db"
    with SQLiteEventStore(path) as store:
        store.append_batch(
            "main",
            [
                NewEvent(tick=0, phase="test", event_type="root.a"),
                NewEvent(tick=1, phase="test", event_type="root.b"),
            ],
            expected_sequence=0,
        )
        store.create_timeline("first-crisis", parent_timeline_id="main")
        store.append_batch(
            "first-crisis",
            [NewEvent(tick=2, phase="test", event_type="memory.experience")],
            expected_sequence=2,
        )
        store.create_timeline(
            "second-crisis",
            parent_timeline_id="first-crisis",
            parent_through_sequence=3,
        )
        store.append_batch(
            "second-crisis",
            [NewEvent(tick=3, phase="test", event_type="second.crisis")],
            expected_sequence=3,
        )

        assert [event.event_type for event in store.read("second-crisis")] == [
            "root.a",
            "root.b",
            "memory.experience",
            "second.crisis",
        ]
        assert store.timeline("second-crisis").parent_timeline_id == "first-crisis"

        lineage = timeline_lineage(store, "second-crisis")
        assert lineage["depth"] == 2
        assert lineage["root_timeline_id"] == "main"
        assert [item["timeline_id"] for item in lineage["lineage"]] == [
            "main",
            "first-crisis",
            "second-crisis",
        ]
        assert lineage["lineage"][1]["parent_through_sequence"] == 2
        assert lineage["lineage"][2]["parent_through_sequence"] == 3


def test_nested_branch_cutoff_excludes_later_parent_events(tmp_path) -> None:
    path = tmp_path / "world.db"
    with SQLiteEventStore(path) as store:
        store.append_batch("main", [NewEvent(tick=0, phase="test", event_type="root")])
        store.create_timeline("parent", parent_timeline_id="main")
        store.append_batch("parent", [NewEvent(tick=1, phase="test", event_type="kept")], expected_sequence=1)
        store.create_timeline("child", parent_timeline_id="parent", parent_through_sequence=2)
        store.append_batch("parent", [NewEvent(tick=2, phase="test", event_type="later-parent")], expected_sequence=2)

        assert [event.event_type for event in store.read("child")] == ["root", "kept"]
