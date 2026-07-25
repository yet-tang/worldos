from __future__ import annotations

from pathlib import Path

from worldos_core.events import NewEvent
from worldos_core.living_world import (
    ACTOR_IDS,
    LOCATIONS,
    initialize_first_living_world,
    run_first_living_world,
)
from worldos_core.runner import WorldRunner
from worldos_core.sqlite_store import SQLiteEventStore
from worldos_core.world import replay_world


def test_bootstrap_has_three_locations_and_twelve_residents(tmp_path: Path) -> None:
    database = tmp_path / "living.db"
    initialize_first_living_world(database)

    with SQLiteEventStore(database) as store:
        world = replay_world(store.read("main"))

    assert tuple(world.flags["locations"]) == LOCATIONS
    assert set(LOCATIONS).issubset(world.entities)
    assert set(ACTOR_IDS).issubset(world.entities)
    assert sum(entity.kind == "character" for entity in world.entities.values()) == 12


def test_living_world_restarts_branches_and_exposes_narrator(tmp_path: Path) -> None:
    report = run_first_living_world(
        tmp_path / "living.db",
        ticks=20,
        restart_at=7,
        branch_timeline_id="alternate",
    )

    assert report.ticks == 20
    assert report.restart_verified is True
    assert report.actor_count == 12
    assert report.location_count == 3
    assert report.branch_timeline_id == "alternate"
    assert 0 < report.branch_event_count < report.event_count
    assert report.narrator_event_count > 0
    assert report.perspective_event_count >= 0


def test_living_world_is_deterministic_across_databases(tmp_path: Path) -> None:
    left = run_first_living_world(tmp_path / "left.db", ticks=12, restart_at=5, branch_timeline_id="left-alt")
    right = run_first_living_world(tmp_path / "right.db", ticks=12, restart_at=5, branch_timeline_id="right-alt")

    assert left.world_hash == right.world_hash
    assert left.event_count == right.event_count


def test_persistent_kernel_survives_ten_thousand_ticks(tmp_path: Path) -> None:
    """Long-run persistence guard without multiplying cognition history.

    Living behavior is covered above. This test deactivates residents before the long
    clock run so CI validates 10,000 durable ticks, snapshots, restart, and replay in
    bounded time and storage.
    """
    database = tmp_path / "long-run.db"
    initialize_first_living_world(database)
    with SQLiteEventStore(database) as store:
        history = store.read("main")
        store.append_batch(
            "main",
            [
                NewEvent(
                    tick=0,
                    phase="test-fixture",
                    event_type="entity.deactivated",
                    subject_ids=(actor_id,),
                )
                for actor_id in ACTOR_IDS
            ],
            expected_sequence=len(history),
        )

    with WorldRunner(database, snapshot_interval=1_000) as runner:
        runner.run(5_000)
    with WorldRunner(database, snapshot_interval=1_000) as runner:
        result = runner.run(5_000)
        assert result.status.last_completed_tick == 10_000
        assert result.status.latest_snapshot_sequence is not None

    with SQLiteEventStore(database) as store:
        history = store.read("main")
        assert sum(event.event_type == "tick.completed" for event in history) == 10_000
        replay_world(history)
