from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel

from .events import NewEvent
from .inspector import WorldInspector
from .narrator import NarratorReadAPI
from .runner import WorldRunner
from .sqlite_store import SQLiteEventStore
from .world import replay_world


LOCATIONS = ("farm", "market", "homes")
ACTOR_IDS = tuple(f"resident-{index:02d}" for index in range(1, 13))


class LivingWorldReport(BaseModel):
    database_path: str
    timeline_id: str
    ticks: int
    actor_count: int
    location_count: int
    event_count: int
    world_hash: str
    restart_verified: bool
    branch_timeline_id: str
    branch_event_count: int
    branch_world_hash: str
    narrator_event_count: int
    perspective_event_count: int
    metrics: dict[str, Any]


def bootstrap_events() -> list[NewEvent]:
    events = [
        NewEvent(
            tick=0,
            phase="bootstrap",
            event_type="world.created",
            payload={
                "flags": {
                    "world_name": "First Living World",
                    "locations": list(LOCATIONS),
                    "scenario_version": 1,
                }
            },
        )
    ]
    for location_id in LOCATIONS:
        events.append(
            NewEvent(
                tick=0,
                phase="bootstrap",
                event_type="entity.created",
                subject_ids=(location_id,),
                payload={"kind": "location", "components": {"name": location_id}},
            )
        )

    jobs = (
        ("food", 2),
        ("food", 1),
        ("wood", 2),
        ("wood", 1),
        ("cloth", 1),
        ("tools", 1),
    )
    for index, actor_id in enumerate(ACTOR_IDS):
        location_id = LOCATIONS[index % len(LOCATIONS)]
        resource, rate = jobs[index % len(jobs)]
        components: dict[str, Any] = {
            "position": {"location_id": location_id},
            "health": {"current": 100, "maximum": 100},
            "needs": {"hunger": index % 20, "fatigue": (index * 3) % 25},
            "survival": {"hunger": index % 20, "fatigue": (index * 3) % 25},
            "metabolism": {"hunger_per_tick": 1, "fatigue_per_tick": 1},
            "inventory": {resource: 4 + index % 3, "food": 2},
            "wallet": 20 + index,
            "job": {"resource": resource, "rate": rate},
            "relationships": {},
            "rumors": ["the old well may be running dry"] if index == 0 else [],
            "identity": {"name": f"Resident {index + 1}", "home": "homes"},
        }
        if index == 0:
            components["trade_offer"] = {
                "buyer_id": ACTOR_IDS[3],
                "resource": "food",
                "quantity": 1,
                "price": 2,
            }
        if index == 1:
            components["conflict"] = {"target_id": ACTOR_IDS[4], "severity": 20}
        events.append(
            NewEvent(
                tick=0,
                phase="bootstrap",
                event_type="entity.created",
                subject_ids=(actor_id,),
                payload={"kind": "character", "components": components},
            )
        )
    return events


def initialize_first_living_world(database_path: str | Path) -> None:
    with SQLiteEventStore(database_path) as store:
        history = store.read("main")
        if history:
            world = replay_world(history)
            if world.flags.get("world_name") != "First Living World":
                raise ValueError("database already contains a different world")
            return
        events = bootstrap_events()
        store.append_batch("main", events, expected_sequence=0)


def run_first_living_world(
    database_path: str | Path,
    *,
    ticks: int = 10_000,
    world_seed: str = "first-living-world",
    restart_at: int | None = None,
    branch_timeline_id: str = "living-world-alternate",
) -> LivingWorldReport:
    if ticks < 0:
        raise ValueError("ticks must be non-negative")
    initialize_first_living_world(database_path)
    split = restart_at if restart_at is not None else ticks // 2
    split = max(0, min(ticks, split))

    with WorldRunner(database_path, world_seed=world_seed, snapshot_interval=500) as runner:
        initial_tick = runner.status().last_completed_tick
        first_count = min(split, max(0, ticks - initial_tick))
        if first_count:
            runner.run(first_count)
        checkpoint_status = runner.status()
        checkpoint_sequence = checkpoint_status.event_count

    with WorldRunner(database_path, world_seed=world_seed, snapshot_interval=500) as runner:
        restart_verified = runner.status().last_completed_tick == checkpoint_status.last_completed_tick
        remaining = max(0, ticks - runner.status().last_completed_tick)
        if remaining:
            result = runner.run(remaining)
        else:
            result = runner.step(0)
        status = result.status
        try:
            runner.branch(branch_timeline_id, through_sequence=checkpoint_sequence)
        except Exception:
            runner.store.timeline(branch_timeline_id)
        inspector = WorldInspector(runner.store)
        omniscient = NarratorReadAPI(inspector).context("main")
        perspective = NarratorReadAPI(inspector).context(
            "main", perspective_actor_id=ACTOR_IDS[0]
        )
        branch_snapshot = inspector.snapshot(branch_timeline_id)

        return LivingWorldReport(
            database_path=str(database_path),
            timeline_id="main",
            ticks=status.last_completed_tick,
            actor_count=len(ACTOR_IDS),
            location_count=len(LOCATIONS),
            event_count=status.event_count,
            world_hash=status.world_hash,
            restart_verified=restart_verified,
            branch_timeline_id=branch_timeline_id,
            branch_event_count=branch_snapshot.event_count,
            branch_world_hash=branch_snapshot.world_hash,
            narrator_event_count=len(omniscient.events),
            perspective_event_count=len(perspective.events),
            metrics=status.metrics.model_dump(mode="json"),
        )
