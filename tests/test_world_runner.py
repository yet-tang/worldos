from pathlib import Path

from worldos_core.events import NewEvent
from worldos_core.runner import WorldRunner
from worldos_core.sqlite_store import SQLiteEventStore
from worldos_core.world import replay_world


def _bootstrap(path: Path) -> None:
    with SQLiteEventStore(path) as store:
        store.append_batch(
            "main",
            [
                NewEvent(
                    tick=0,
                    phase="bootstrap",
                    event_type="world.created",
                    payload={"flags": {"name": "runner-test"}},
                ),
                NewEvent(
                    tick=0,
                    phase="bootstrap",
                    event_type="entity.created",
                    subject_ids=("worker",),
                    payload={
                        "kind": "character",
                        "components": {
                            "position": {"location_id": "farm"},
                            "health": {"current": 100, "maximum": 100},
                            "needs": {"hunger": 0, "fatigue": 0},
                            "metabolism": {"hunger_per_tick": 1, "fatigue_per_tick": 1},
                            "job": {"resource": "food", "rate": 1},
                            "inventory": {},
                            "wallet": 0,
                        },
                    },
                ),
            ],
            expected_sequence=0,
        )


def test_runner_restarts_and_continues_from_last_completed_tick(tmp_path: Path) -> None:
    database = tmp_path / "world.db"
    _bootstrap(database)

    with WorldRunner(database, snapshot_interval=1) as runner:
        first = runner.run(2)
        assert [result.tick for result in first.tick_results] == [1, 2]
        assert first.status.last_completed_tick == 2
        assert first.status.latest_snapshot_sequence == first.status.event_count

    with WorldRunner(database, snapshot_interval=1) as runner:
        second = runner.run(1)
        assert [result.tick for result in second.tick_results] == [3]
        assert second.status.last_completed_tick == 3
        world = replay_world(runner.store.read(runner.timeline_id))
        assert world.entities["worker"].components["inventory"]["food"] == 3


def test_pause_stops_run_but_step_and_resume_continue(tmp_path: Path) -> None:
    database = tmp_path / "world.db"
    _bootstrap(database)

    with WorldRunner(database) as runner:
        assert runner.pause().paused is True
        stopped = runner.run(5)
        assert stopped.tick_results == ()
        assert stopped.status.last_completed_tick == 0

        stepped = runner.step(1)
        assert stepped.status.last_completed_tick == 1
        assert stepped.status.paused is True

        assert runner.resume().paused is False
        continued = runner.run(1)
        assert continued.status.last_completed_tick == 2


def test_runner_creates_persistent_branch(tmp_path: Path) -> None:
    database = tmp_path / "world.db"
    _bootstrap(database)

    with WorldRunner(database) as runner:
        runner.run(1)
        cutoff = runner.status().event_count
        runner.branch("experiment", through_sequence=cutoff, switch=True)
        runner.run(1)
        assert runner.timeline_id == "experiment"
        assert runner.status().last_completed_tick == 2
        assert len(runner.store.read("main")) == cutoff
        assert len(runner.store.read("experiment")) > cutoff

    with SQLiteEventStore(database) as store:
        assert store.timeline("experiment").parent_timeline_id == "main"


def test_recovery_branches_before_incomplete_tick(tmp_path: Path) -> None:
    database = tmp_path / "world.db"
    _bootstrap(database)

    with WorldRunner(database) as runner:
        runner.run(1)
        stable_count = runner.status().event_count
        runner.store.append_batch(
            "main",
            [
                NewEvent(
                    tick=2,
                    phase="scheduler",
                    event_type="tick.started",
                    payload={"tick": 2},
                ),
                NewEvent(
                    tick=2,
                    phase="effects",
                    event_type="world.flag_set",
                    payload={"name": "partial_effect", "value": True},
                ),
            ],
            expected_sequence=stable_count,
        )

    with WorldRunner(database) as recovered:
        assert recovered.timeline_id == "main-recovery-1"
        assert recovered.status().recovered_from_timeline == "main"
        assert recovered.store.timeline(recovered.timeline_id).parent_through_sequence == stable_count
        world = replay_world(recovered.store.read(recovered.timeline_id))
        assert "partial_effect" not in world.flags
        assert recovered.run(1).status.last_completed_tick == 2


def test_session_metrics_are_reported_without_entering_world_history(tmp_path: Path) -> None:
    database = tmp_path / "world.db"
    _bootstrap(database)

    with WorldRunner(database) as runner:
        result = runner.run(2)
        assert result.status.metrics.ticks_run == 2
        assert result.status.metrics.events_committed > 0
        assert result.status.metrics.elapsed_seconds >= 0
        assert all(
            event.event_type != "runner.metric"
            for event in runner.store.read(runner.timeline_id)
        )
