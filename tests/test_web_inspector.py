from worldos_core.events import NewEvent
from worldos_core.sqlite_store import SQLiteEventStore
from worldos_core.web_inspector import HTML, WebInspectorService


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
                        "identity": {"name": "Alice"},
                        "position": {"location_id": "market"},
                        "health": {"current": 90, "maximum": 100},
                        "needs": {"hunger": 12, "fatigue": 8},
                        "wallet": 20,
                        "job": {"resource": "food", "rate": 2},
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
            NewEvent(tick=7, phase="scheduler", event_type="tick.started", payload={"tick": 7}),
            NewEvent(tick=7, phase="scheduler", event_type="tick.completed", payload={"tick": 7}),
        ],
        expected_sequence=0,
    )


def test_inspector_html_defaults_to_chinese_and_keeps_english_toggle():
    assert '<html lang="zh-CN">' in HTML
    assert "WorldOS 世界观察台" in HTML
    assert "只读观察模式" in HTML
    assert "English" in HTML
    assert "localStorage.getItem('worldos.lang')" in HTML


def test_overview_exposes_map_actors_and_relationships(tmp_path):
    with SQLiteEventStore(tmp_path / "world.db") as store:
        bootstrap(store)
        service = WebInspectorService(store)
        overview = service.overview()

        assert overview["summary"]["entity_count"] == 2
        assert overview["summary"]["world_name"] == "Town"
        assert overview["summary"]["current_tick"] == 7
        assert overview["map"] == {"market": ["alice", "bob"]}
        assert [actor["actor_id"] for actor in overview["actors"]] == ["alice", "bob"]
        alice = overview["actors"][0]
        assert alice["name"] == "Alice"
        assert alice["active"] is True
        assert alice["health"] == {"current": 90, "maximum": 100}
        assert alice["needs"] == {"hunger": 12, "fatigue": 8}
        assert alice["wallet"] == 20
        assert alice["job"] == {"resource": "food", "rate": 2}
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
        store.create_timeline("alternate", parent_through_sequence=5)
        store.append_batch(
            "alternate",
            [
                NewEvent(
                    tick=8,
                    phase="consequence",
                    event_type="entity.component_set",
                    subject_ids=("alice",),
                    payload={"component": "position", "value": {"location_id": "home"}},
                )
            ],
            expected_sequence=5,
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
