from __future__ import annotations

import argparse
import json
from typing import Any

from .events import NewEvent
from .inspector import WorldInspector
from .narrator import NarratorReadAPI
from .runner import WorldRunner
from .scheduler import DeterministicTickEngine
from .sqlite_store import SQLiteEventStore
from .store import InMemoryEventStore
from .world import replay_world


def _json_default(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, tuple):
        return list(value)
    raise TypeError(f"Object of type {value.__class__.__name__} is not JSON serializable")


def _dump(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=_json_default))


def build_demo_store(*, ticks: int = 1, world_seed: str = "worldos-demo") -> InMemoryEventStore:
    """Build a deterministic, fully in-memory example world."""
    if ticks < 0:
        raise ValueError("ticks must be non-negative")

    store = InMemoryEventStore()
    store.append_batch(
        "main",
        [
            NewEvent(
                tick=0,
                phase="bootstrap",
                event_type="world.created",
                payload={"flags": {"weather": "snow"}},
            ),
            NewEvent(
                tick=0,
                phase="bootstrap",
                event_type="entity.created",
                subject_ids=("traveler",),
                payload={
                    "kind": "human",
                    "components": {
                        "position": {"location_id": "hall"},
                        "health": {"current": 100, "maximum": 100},
                    },
                },
            ),
            NewEvent(
                tick=0,
                phase="bootstrap",
                event_type="entity.created",
                subject_ids=("witness",),
                payload={
                    "kind": "human",
                    "components": {
                        "position": {"location_id": "hall"},
                        "health": {"current": 100, "maximum": 100},
                    },
                },
            ),
            NewEvent(
                tick=0,
                phase="cognition",
                event_type="goal.created",
                actor_id="traveler",
                subject_ids=("traveler",),
                payload={
                    "goal_id": "reach-room",
                    "owner_id": "traveler",
                    "goal_type": "reach_location",
                    "priority": 10,
                    "parameters": {"location_id": "room_2"},
                    "created_tick": 0,
                },
            ),
        ],
        expected_sequence=0,
    )

    engine = DeterministicTickEngine(store, world_seed=world_seed)
    for tick in range(1, ticks + 1):
        engine.run_tick("main", tick)
    return store


def demo() -> None:
    store = build_demo_store(ticks=1)
    main = replay_world(store.read("main"))

    branch_at = len(store.read("main"))
    store.create_timeline(
        "alternate",
        parent_timeline_id="main",
        parent_through_sequence=branch_at,
    )
    store.append_batch(
        "alternate",
        [
            NewEvent(
                tick=2,
                phase="consequence",
                event_type="world.flag_set",
                payload={"name": "door_locked", "value": True},
            )
        ],
        expected_sequence=branch_at,
    )
    branch = replay_world(store.read("alternate"))

    _dump(
        {
            "main": {
                "hash": main.canonical_hash(),
                "traveler": main.entities["traveler"].model_dump(mode="json"),
            },
            "alternate": {
                "hash": branch.canonical_hash(),
                "flags": branch.flags,
            },
        }
    )


def simulate(ticks: int, seed: str) -> None:
    store = build_demo_store(ticks=ticks, world_seed=seed)
    inspector = WorldInspector(store)
    snapshot = inspector.snapshot("main")
    _dump(
        {
            "timeline_id": "main",
            "ticks": ticks,
            "event_count": snapshot.event_count,
            "world_hash": snapshot.world_hash,
            "world": snapshot.world,
        }
    )


def inspect(actor_id: str, ticks: int, seed: str) -> None:
    store = build_demo_store(ticks=ticks, world_seed=seed)
    _dump(WorldInspector(store).actor(actor_id, "main"))


def narrate(actor_id: str | None, ticks: int, seed: str) -> None:
    store = build_demo_store(ticks=ticks, world_seed=seed)
    api = NarratorReadAPI(WorldInspector(store))
    _dump(api.context("main", perspective_actor_id=actor_id))


def initialize_persistent_world(database: str) -> None:
    with SQLiteEventStore(database) as store:
        if store.read("main"):
            raise ValueError("main timeline is already initialized")
        store.append_batch(
            "main",
            [
                NewEvent(
                    tick=0,
                    phase="bootstrap",
                    event_type="world.created",
                    payload={"flags": {"world_name": "First Living World"}},
                )
            ],
            expected_sequence=0,
        )
    _dump({"database": database, "timeline_id": "main", "initialized": True})


def runner_command(command: str, database: str, timeline: str, seed: str, **options: Any) -> None:
    with WorldRunner(
        database,
        timeline_id=timeline,
        world_seed=seed,
        snapshot_interval=int(options.get("snapshot_interval", 100)),
    ) as runner:
        if command == "run":
            _dump(runner.run(int(options["ticks"])).status)
        elif command == "step":
            _dump(runner.step(int(options["ticks"])).status)
        elif command == "pause":
            _dump(runner.pause())
        elif command == "resume":
            _dump(runner.resume())
        elif command == "status":
            _dump(runner.status())
        elif command == "branch":
            branch_id = str(options["branch_id"])
            runner.branch(
                branch_id,
                through_sequence=options.get("through_sequence"),
            )
            _dump({"source_timeline_id": timeline, "branch_timeline_id": branch_id})


def _add_runner_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--db", required=True, help="SQLite world database")
    parser.add_argument("--timeline", default="main")
    parser.add_argument("--seed", default="worldos")


def main() -> None:
    parser = argparse.ArgumentParser(prog="worldos-core")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("demo", help="run the branching architecture demo")

    simulate_parser = subparsers.add_parser("simulate", help="run a deterministic example world")
    simulate_parser.add_argument("--ticks", type=int, default=1)
    simulate_parser.add_argument("--seed", default="worldos-demo")

    inspect_parser = subparsers.add_parser("inspect", help="inspect one actor after simulation")
    inspect_parser.add_argument("actor_id")
    inspect_parser.add_argument("--ticks", type=int, default=1)
    inspect_parser.add_argument("--seed", default="worldos-demo")

    narrate_parser = subparsers.add_parser("narrate", help="emit read-only narrative context")
    narrate_parser.add_argument("--actor", dest="actor_id")
    narrate_parser.add_argument("--ticks", type=int, default=1)
    narrate_parser.add_argument("--seed", default="worldos-demo")

    init_parser = subparsers.add_parser("world-init", help="initialize a persistent SQLite world")
    init_parser.add_argument("--db", required=True)

    run_parser = subparsers.add_parser("run", help="run persistent world ticks until paused or count reached")
    _add_runner_common(run_parser)
    run_parser.add_argument("--ticks", type=int, default=1)
    run_parser.add_argument("--snapshot-interval", type=int, default=100)

    step_parser = subparsers.add_parser("step", help="advance persistent world even when paused")
    _add_runner_common(step_parser)
    step_parser.add_argument("--ticks", type=int, default=1)
    step_parser.add_argument("--snapshot-interval", type=int, default=100)

    for name in ("pause", "resume", "status"):
        control_parser = subparsers.add_parser(name, help=f"{name} a persistent world")
        _add_runner_common(control_parser)

    branch_parser = subparsers.add_parser("branch", help="create a persistent timeline branch")
    _add_runner_common(branch_parser)
    branch_parser.add_argument("branch_id")
    branch_parser.add_argument("--through-sequence", type=int)

    args = parser.parse_args()
    if args.command == "demo":
        demo()
    elif args.command == "simulate":
        simulate(args.ticks, args.seed)
    elif args.command == "inspect":
        inspect(args.actor_id, args.ticks, args.seed)
    elif args.command == "narrate":
        narrate(args.actor_id, args.ticks, args.seed)
    elif args.command == "world-init":
        initialize_persistent_world(args.db)
    elif args.command in {"run", "step"}:
        runner_command(
            args.command,
            args.db,
            args.timeline,
            args.seed,
            ticks=args.ticks,
            snapshot_interval=args.snapshot_interval,
        )
    elif args.command in {"pause", "resume", "status"}:
        runner_command(args.command, args.db, args.timeline, args.seed)
    elif args.command == "branch":
        runner_command(
            "branch",
            args.db,
            args.timeline,
            args.seed,
            branch_id=args.branch_id,
            through_sequence=args.through_sequence,
        )


if __name__ == "__main__":
    main()
