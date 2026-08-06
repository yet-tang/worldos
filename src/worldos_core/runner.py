from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time
from typing import Iterable

from pydantic import BaseModel, Field

from .events import Event, NewEvent
from .modules import WorldModule
from .scheduler import DeterministicTickEngine, TickResult
from .sqlite_store import SQLiteEventStore
from .store import EventStoreError
from .survival import SurvivalEconomyModule
from .world import replay_world


class RunnerMetrics(BaseModel):
    ticks_run: int = 0
    events_committed: int = 0
    elapsed_seconds: float = 0.0
    ticks_per_second: float = 0.0


class RunnerStatus(BaseModel):
    database_path: str
    timeline_id: str
    paused: bool
    last_completed_tick: int
    event_count: int
    world_hash: str
    latest_snapshot_sequence: int | None = None
    recovered_from_timeline: str | None = None
    metrics: RunnerMetrics = Field(default_factory=RunnerMetrics)


@dataclass(frozen=True)
class RunResult:
    timeline_id: str
    tick_results: tuple[TickResult, ...]
    status: RunnerStatus


class WorldRunner:
    """Persistent controller for deterministic WorldOS timelines.

    Runner control events are audit-only. Authoritative world changes remain owned by
    the tick engine and world modules. If a process dies after ``tick.started`` but
    before ``tick.completed``, recovery creates a branch immediately before the
    incomplete tick and continues there, preserving the damaged history for audit.
    """

    def __init__(
        self,
        database_path: str | Path,
        *,
        timeline_id: str = "main",
        world_seed: str | int = "worldos",
        snapshot_interval: int = 100,
        modules: Iterable[WorldModule] | None = None,
        auto_recover: bool = True,
    ) -> None:
        if snapshot_interval < 0:
            raise ValueError("snapshot_interval must be non-negative")
        self.database_path = Path(database_path)
        self.store = SQLiteEventStore(self.database_path)
        self.timeline_id = timeline_id
        self.world_seed = world_seed
        self.snapshot_interval = snapshot_interval
        configured_modules = tuple(modules) if modules is not None else (SurvivalEconomyModule(),)
        self.engine = DeterministicTickEngine(
            self.store,
            world_seed=world_seed,
            modules=configured_modules,
        )
        self._metrics = RunnerMetrics()
        self._recovered_from_timeline: str | None = None
        self.store.timeline(timeline_id)
        if auto_recover:
            self.recover()

    def close(self) -> None:
        self.store.close()

    def __enter__(self) -> WorldRunner:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def status(self) -> RunnerStatus:
        history = self.store.read(self.timeline_id)
        world = replay_world(history)
        snapshot = self.store.latest_snapshot(self.timeline_id, "world")
        return RunnerStatus(
            database_path=str(self.database_path),
            timeline_id=self.timeline_id,
            paused=self._paused(history),
            last_completed_tick=self._last_completed_tick(history),
            event_count=len(history),
            world_hash=world.canonical_hash(),
            latest_snapshot_sequence=snapshot.sequence if snapshot else None,
            recovered_from_timeline=self._recovered_from_timeline,
            metrics=self._metrics.model_copy(deep=True),
        )

    def pause(self) -> RunnerStatus:
        if not self.status().paused:
            self._append_control("runner.paused", {"timeline_id": self.timeline_id})
        return self.status()

    def resume(self) -> RunnerStatus:
        if self.status().paused:
            self._append_control("runner.resumed", {"timeline_id": self.timeline_id})
        return self.status()

    def step(self, count: int = 1, *, force: bool = True) -> RunResult:
        if count < 0:
            raise ValueError("count must be non-negative")
        results: list[TickResult] = []
        started = time.perf_counter()
        for _ in range(count):
            current = self.status()
            if current.paused and not force:
                break
            tick = current.last_completed_tick + 1
            result = self.engine.run_tick(self.timeline_id, tick)
            results.append(result)
            if self.snapshot_interval and tick % self.snapshot_interval == 0:
                self.save_snapshot()
        elapsed = time.perf_counter() - started
        events = sum(len(result.committed_events) for result in results)
        total_ticks = self._metrics.ticks_run + len(results)
        total_events = self._metrics.events_committed + events
        total_elapsed = self._metrics.elapsed_seconds + elapsed
        self._metrics = RunnerMetrics(
            ticks_run=total_ticks,
            events_committed=total_events,
            elapsed_seconds=total_elapsed,
            ticks_per_second=(total_ticks / total_elapsed) if total_elapsed > 0 else 0.0,
        )
        return RunResult(self.timeline_id, tuple(results), self.status())

    def run(self, ticks: int) -> RunResult:
        """Run at most ``ticks`` ticks, stopping early when the timeline is paused."""
        return self.step(ticks, force=False)

    def save_snapshot(self) -> int:
        history = self.store.read(self.timeline_id)
        world = replay_world(history)
        snapshot = self.store.save_snapshot(
            self.timeline_id,
            len(history),
            "world",
            world.model_dump(mode="json"),
        )
        return snapshot.sequence

    def branch(
        self,
        timeline_id: str,
        *,
        through_sequence: int | None = None,
        switch: bool = False,
    ) -> str:
        self.store.create_timeline(
            timeline_id,
            parent_timeline_id=self.timeline_id,
            parent_through_sequence=through_sequence,
        )
        if switch:
            self.timeline_id = timeline_id
        return timeline_id

    def recover(self) -> str | None:
        history = self.store.read(self.timeline_id)
        completed_ticks = {
            event.tick for event in history if event.event_type == "tick.completed"
        }
        incomplete = [
            event
            for event in history
            if event.event_type == "tick.started" and event.tick not in completed_ticks
        ]
        if not incomplete:
            return None
        start = incomplete[-1]
        source_timeline = self.timeline_id
        cutoff = start.sequence - 1
        recovery_timeline = self._next_recovery_timeline(source_timeline)
        self.store.create_timeline(
            recovery_timeline,
            parent_timeline_id=source_timeline,
            parent_through_sequence=cutoff,
        )
        self.timeline_id = recovery_timeline
        self._recovered_from_timeline = source_timeline
        self._append_control(
            "runner.recovered",
            {
                "source_timeline_id": source_timeline,
                "discarded_from_sequence": start.sequence,
                "incomplete_tick": start.tick,
            },
        )
        return recovery_timeline

    def _next_recovery_timeline(self, source_timeline: str) -> str:
        index = 1
        while True:
            candidate = f"{source_timeline}-recovery-{index}"
            try:
                self.store.timeline(candidate)
            except EventStoreError:
                return candidate
            index += 1

    def _append_control(self, event_type: str, payload: dict[str, object]) -> Event:
        history = self.store.read(self.timeline_id)
        event = NewEvent(
            tick=self._last_completed_tick(history),
            phase="runner",
            event_type=event_type,
            payload=payload,
        )
        committed = self.store.append_batch(
            self.timeline_id,
            [event],
            expected_sequence=len(history),
        )[0]
        # Control events are written outside the tick engine. Drop its cached history
        # so the next tick observes the new sequence and preserves optimistic locking.
        self.engine.invalidate_cache(self.timeline_id)
        return committed

    @staticmethod
    def _last_completed_tick(history: list[Event]) -> int:
        completed = [event.tick for event in history if event.event_type == "tick.completed"]
        return max(completed, default=0)

    @staticmethod
    def _paused(history: list[Event]) -> bool:
        control = [
            event
            for event in history
            if event.event_type in {"runner.paused", "runner.resumed"}
        ]
        return bool(control and control[-1].event_type == "runner.paused")
