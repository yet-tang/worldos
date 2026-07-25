from worldos_core.events import NewEvent
from worldos_core.sqlite_store import SQLiteEventStore
from worldos_core.web_inspector import WebInspectorService


def bootstrap(store: SQLiteEventStore) -> None:
    store.append_batch(
        "main",
        [
            NewEvent(tick=0, phase="bootstrap", event_type="world.created", payload={"flags": {"name": "Town"}}),
            NewEvent(
                tick=0,
                phase="bootstrap",
                event_type="entity.created",
                subject_ids=("alice",),
                payload={
                    "kind": "human",
                    "components": {
                        "position": {"location_id": "market"},
                        "health": {"current": 90, "maximum": 100},
                        "relationships": {"bob": 3},
                    },
                },
            ),
            NewEvent(
                tick=0,
                phase="bootstrap",
                event_type="entity.created",
                subject_ids=("bob",),
                payload={"kind": "human", "components": {"position": {"location_id": "market"}}},
            ),
        ],
        expected_sequence=0,
    )


def test_overview_exposes_map_actors_and_relationships(tmp_path):
    with SQLiteEventStore(tmp_path / "world.db") as store:
        bootstrap(store)
        service = WebInspectorService(store)
        overview = service.overview()

        assert overview["summary"]["entity_count"] == 2
        assert overview["map"] == {"market": ["alice", "bob"]}
        assert [actor["actor_id"] for actor in overview["actors"]] == ["alice", "bob"]
        assert overview["relationships"] == {"alice": {"bob": 3}}


def test_actor_events_and_narrator_are_read_only(tmp_path):
    with SQLiteEventStore(tmp_path / "world.db") as store:
        bootstrap(store)
        before = len(store.read("main"))
        service = WebInspectorService(store)

        actor = service.actor("alice")
        events = service.events(limit=2)
        narrative = service.narrative()

        assert actor["actor_id"] == "alice"
        assert actor["entity"]["components"]["health"]["current"] == 90
        assert len(events) == 2
        assert narrative["mode"] == "omniscient"
        assert len(store.read("main")) == before


def test_compare_reports_changed_entities_between_branches(tmp_path):
    with SQLiteEventStore(tmp_path / "world.db") as store:
        bootstrap(store)
        store.create_timeline("alternate", parent_through_sequence=3)
        store.append_batch(
            "alternate",
            [
                NewEvent(
                    tick=1,
                    phase="consequence",
                    event_type="entity.component_set",
                    subject_ids=("alice",),
                    payload={"component": "position", "value": {"location_id": "home"}},
                )
            ],
            expected_sequence=3,
        )

        comparison = WebInspectorService(store).compare("main", "alternate")

        assert comparison["same_world"] is False
        assert comparison["changed_entities"] == ["alice"]


def test_event_limit_is_bounded(tmp_path):
    with SQLiteEventStore(tmp_path / "world.db") as store:
        bootstrap(store)
        service = WebInspectorService(store)

        for invalid in (0, 5001):
            try:
                service.events(limit=invalid)
            except ValueError as exc:
                assert "between 1 and 5000" in str(exc)
            else:
                raise AssertionError("invalid limit was accepted")
