from __future__ import annotations

import argparse
import json
from typing import Any

from .events import NewEvent
from .inspector import WorldInspector
from .narrator import NarratorReadAPI
from .scheduler import DeterministicTickEngine
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

    args = parser.parse_args()
    if args.command == "demo":
        demo()
    elif args.command == "simulate":
        simulate(args.ticks, args.seed)
    elif args.command == "inspect":
        inspect(args.actor_id, args.ticks, args.seed)
    elif args.command == "narrate":
        narrate(args.actor_id, args.ticks, args.seed)


if __name__ == "__main__":
    main()
