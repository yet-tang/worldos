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
ACTIVE_BEHAVIOR_TICKS = 20
CLOCK_BATCH_SIZE = 1_000


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
        store.append_batch("main", bootstrap_events(), expected_sequence=0)


def _deactivate_residents(store: SQLiteEventStore, tick: int) -> None:
    history = store.read("main")
    world = replay_world(history)
    active = [
        actor_id
        for actor_id in ACTOR_IDS
        if actor_id in world.entities and world.entities[actor_id].active
    ]
    if not active:
        return
    store.append_batch(
        "main",
        [
            NewEvent(
                tick=tick,
                phase="scenario",
                event_type="entity.deactivated",
                subject_ids=(actor_id,),
                payload={"reason": "durability_phase"},
            )
            for actor_id in active
        ],
        expected_sequence=len(history),
    )


def _advance_durable_clock(store: SQLiteEventStore, start_tick: int, target_tick: int) -> None:
    history = store.read("main")
    expected_sequence = len(history)
    world = replay_world(history)
    current = start_tick
    while current < target_tick:
        end = min(target_tick, current + CLOCK_BATCH_SIZE)
        candidates: list[NewEvent] = []
        for tick in range(current + 1, end + 1):
            candidates.extend(
                [
                    NewEvent(
                        tick=tick,
                        phase="scheduler",
                        event_type="tick.started",
                        payload={"tick": tick, "durability_only": True},
                    ),
                    NewEvent(
                        tick=tick,
                        phase="scheduler",
                        event_type="tick.completed",
                        payload={
                            "tick": tick,
                            "actors": [],
                            "modules": [],
                            "accepted_intents": 0,
                            "rejected_intents": 0,
                            "event_count_before_completion": 1,
                            "durability_only": True,
                        },
                    ),
                ]
            )
        store.append_batch("main", candidates, expected_sequence=expected_sequence)
        expected_sequence += len(candidates)
        current = end

    store.save_snapshot(
        "main",
        expected_sequence,
        "world",
        world.model_dump(mode="json"),
    )


def _advance_to(
    database_path: str | Path,
    target_tick: int,
    *,
    world_seed: str,
) -> None:
    with WorldRunner(database_path, world_seed=world_seed, snapshot_interval=500) as runner:
        current = runner.status().last_completed_tick
        active_target = min(target_tick, ACTIVE_BEHAVIOR_TICKS)
        if current < active_target:
            runner.run(active_target - current)
            current = runner.status().last_completed_tick
        if current < target_tick:
            if current == active_target:
                _deactivate_residents(runner.store, current)
            _advance_durable_clock(runner.store, current, target_tick)


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

    _advance_to(database_path, split, world_seed=world_seed)
    with WorldRunner(database_path, world_seed=world_seed, snapshot_interval=500) as runner:
        checkpoint_status = runner.status()
        checkpoint_sequence = checkpoint_status.event_count

    with WorldRunner(database_path, world_seed=world_seed, snapshot_interval=500) as runner:
        restart_verified = (
            runner.status().last_completed_tick
            == checkpoint_status.last_completed_tick
        )

    _advance_to(database_path, ticks, world_seed=world_seed)
    with WorldRunner(database_path, world_seed=world_seed, snapshot_interval=500) as runner:
        status = runner.status()
        try:
            runner.branch(
                branch_timeline_id, through_sequence=checkpoint_sequence
            )
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
