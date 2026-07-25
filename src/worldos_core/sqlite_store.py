from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterable, Iterator, Mapping

from .events import Event, NewEvent
from .store import EventStoreError
from .timeline import Timeline


@dataclass(frozen=True)
class StoredSnapshot:
    timeline_id: str
    sequence: int
    projection: str
    state: dict[str, Any]
    state_hash: str


class SQLiteEventStore:
    """Durable Event Store with atomic batches, branches, migrations and snapshots.

    SQLite runs in WAL mode and every append is committed in one ``BEGIN IMMEDIATE``
    transaction. A process that stops between statements therefore exposes either the
    complete event batch or none of it when the database is reopened.
    """

    SCHEMA_VERSION = 1

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path, isolation_level=None)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA journal_mode = WAL")
        self._connection.execute("PRAGMA synchronous = FULL")
        self._migrate()

    def close(self) -> None:
        if self._connection is not None:
            self._connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            self._connection.close()
            self._connection = None  # type: ignore[assignment]

    def __enter__(self) -> SQLiteEventStore:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connection
        connection.execute("BEGIN IMMEDIATE")
        try:
            yield connection
        except BaseException:
            connection.execute("ROLLBACK")
            raise
        else:
            connection.execute("COMMIT")

    def _migrate(self) -> None:
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY)"
        )
        row = self._connection.execute(
            "SELECT COALESCE(MAX(version), 0) AS version FROM schema_migrations"
        ).fetchone()
        current = int(row["version"])
        if current > self.SCHEMA_VERSION:
            raise EventStoreError(
                f"database schema {current} is newer than supported {self.SCHEMA_VERSION}"
            )
        if current < 1:
            with self._transaction() as connection:
                connection.executescript(
                    """
                    CREATE TABLE timelines (
                        timeline_id TEXT PRIMARY KEY,
                        parent_timeline_id TEXT REFERENCES timelines(timeline_id),
                        parent_through_sequence INTEGER NOT NULL DEFAULT 0,
                        CHECK(parent_through_sequence >= 0)
                    );
                    CREATE TABLE events (
                        timeline_id TEXT NOT NULL REFERENCES timelines(timeline_id),
                        sequence INTEGER NOT NULL,
                        event_id TEXT NOT NULL UNIQUE,
                        document TEXT NOT NULL,
                        PRIMARY KEY (timeline_id, sequence)
                    );
                    CREATE INDEX events_timeline_sequence
                        ON events(timeline_id, sequence);
                    CREATE TABLE snapshots (
                        timeline_id TEXT NOT NULL REFERENCES timelines(timeline_id),
                        sequence INTEGER NOT NULL,
                        projection TEXT NOT NULL,
                        state_json TEXT NOT NULL,
                        state_hash TEXT NOT NULL,
                        PRIMARY KEY (timeline_id, sequence, projection)
                    );
                    INSERT INTO timelines(timeline_id, parent_timeline_id, parent_through_sequence)
                        VALUES ('main', NULL, 0);
                    INSERT INTO schema_migrations(version) VALUES (1);
                    """
                )

    def create_timeline(
        self,
        timeline_id: str,
        *,
        parent_timeline_id: str = "main",
        parent_through_sequence: int | None = None,
    ) -> Timeline:
        with self._transaction() as connection:
            if self._timeline_row(timeline_id, connection=connection) is not None:
                raise EventStoreError(f"timeline already exists: {timeline_id}")
            if self._timeline_row(parent_timeline_id, connection=connection) is None:
                raise EventStoreError(f"unknown parent timeline: {parent_timeline_id}")
            parent_count = self._visible_count(parent_timeline_id, connection=connection)
            cutoff = parent_count if parent_through_sequence is None else parent_through_sequence
            if cutoff < 0 or cutoff > parent_count:
                raise EventStoreError("parent cutoff is outside visible history")
            connection.execute(
                "INSERT INTO timelines VALUES (?, ?, ?)",
                (timeline_id, parent_timeline_id, cutoff),
            )
        return Timeline(
            timeline_id=timeline_id,
            parent_timeline_id=parent_timeline_id,
            parent_through_sequence=cutoff,
        )

    def append_batch(
        self,
        timeline_id: str,
        events: Iterable[NewEvent],
        *,
        expected_sequence: int | None = None,
    ) -> list[Event]:
        candidates = list(events)
        with self._transaction() as connection:
            if self._timeline_row(timeline_id, connection=connection) is None:
                raise EventStoreError(f"unknown timeline: {timeline_id}")
            visible_count = self._visible_count(timeline_id, connection=connection)
            if expected_sequence is not None and expected_sequence != visible_count:
                raise EventStoreError(
                    f"optimistic concurrency conflict: expected {expected_sequence}, got {visible_count}"
                )
            committed: list[Event] = []
            for offset, candidate in enumerate(candidates, start=1):
                sequence = visible_count + offset
                event_id = self._event_id(timeline_id, sequence, candidate)
                event = Event(
                    **candidate.model_dump(),
                    event_id=event_id,
                    timeline_id=timeline_id,
                    sequence=sequence,
                )
                connection.execute(
                    "INSERT INTO events(timeline_id, sequence, event_id, document) VALUES (?, ?, ?, ?)",
                    (
                        timeline_id,
                        sequence,
                        event_id,
                        event.model_dump_json(),
                    ),
                )
                committed.append(event)
        return committed

    def read(self, timeline_id: str, through_sequence: int | None = None) -> list[Event]:
        if self._timeline_row(timeline_id) is None:
            raise EventStoreError(f"unknown timeline: {timeline_id}")
        documents = self._read_documents(timeline_id)
        if through_sequence is not None:
            documents = documents[:through_sequence]
        return [Event.model_validate_json(document) for document in documents]

    def timeline(self, timeline_id: str) -> Timeline:
        row = self._timeline_row(timeline_id)
        if row is None:
            raise EventStoreError(f"unknown timeline: {timeline_id}")
        return Timeline(
            timeline_id=row["timeline_id"],
            parent_timeline_id=row["parent_timeline_id"],
            parent_through_sequence=row["parent_through_sequence"],
        )

    def save_snapshot(
        self,
        timeline_id: str,
        sequence: int,
        projection: str,
        state: Mapping[str, Any],
    ) -> StoredSnapshot:
        visible_count = self._visible_count(timeline_id)
        if sequence < 0 or sequence > visible_count:
            raise EventStoreError("snapshot sequence is outside visible history")
        canonical = json.dumps(
            dict(state), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        state_hash = hashlib.sha256(canonical.encode()).hexdigest()
        with self._transaction() as connection:
            connection.execute(
                """
                INSERT INTO snapshots(timeline_id, sequence, projection, state_json, state_hash)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(timeline_id, sequence, projection) DO UPDATE SET
                    state_json = excluded.state_json,
                    state_hash = excluded.state_hash
                """,
                (timeline_id, sequence, projection, canonical, state_hash),
            )
        return StoredSnapshot(timeline_id, sequence, projection, dict(state), state_hash)

    def latest_snapshot(
        self,
        timeline_id: str,
        projection: str,
        *,
        through_sequence: int | None = None,
    ) -> StoredSnapshot | None:
        if self._timeline_row(timeline_id) is None:
            raise EventStoreError(f"unknown timeline: {timeline_id}")
        limit = self._visible_count(timeline_id) if through_sequence is None else through_sequence
        row = self._connection.execute(
            """
            SELECT timeline_id, sequence, projection, state_json, state_hash
            FROM snapshots
            WHERE timeline_id = ? AND projection = ? AND sequence <= ?
            ORDER BY sequence DESC LIMIT 1
            """,
            (timeline_id, projection, limit),
        ).fetchone()
        if row is None:
            return None
        return StoredSnapshot(
            timeline_id=row["timeline_id"],
            sequence=row["sequence"],
            projection=row["projection"],
            state=json.loads(row["state_json"]),
            state_hash=row["state_hash"],
        )

    def integrity_check(self) -> bool:
        row = self._connection.execute("PRAGMA integrity_check").fetchone()
        return row[0] == "ok"

    def _timeline_row(
        self,
        timeline_id: str,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> sqlite3.Row | None:
        active = connection or self._connection
        return active.execute(
            "SELECT timeline_id, parent_timeline_id, parent_through_sequence "
            "FROM timelines WHERE timeline_id = ?",
            (timeline_id,),
        ).fetchone()

    def _visible_count(
        self,
        timeline_id: str,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> int:
        active = connection or self._connection
        row = self._timeline_row(timeline_id, connection=active)
        if row is None:
            raise EventStoreError(f"unknown timeline: {timeline_id}")
        local = active.execute(
            "SELECT COUNT(*) AS count FROM events WHERE timeline_id = ?",
            (timeline_id,),
        ).fetchone()["count"]
        return int(row["parent_through_sequence"]) + int(local)

    def _read_documents(self, timeline_id: str) -> list[str]:
        row = self._timeline_row(timeline_id)
        if row is None:
            raise EventStoreError(f"unknown timeline: {timeline_id}")
        inherited: list[str] = []
        if row["parent_timeline_id"] is not None:
            inherited = self._read_documents(row["parent_timeline_id"])[
                : row["parent_through_sequence"]
            ]
        local = self._connection.execute(
            "SELECT document FROM events WHERE timeline_id = ? ORDER BY sequence",
            (timeline_id,),
        ).fetchall()
        return [*inherited, *(item["document"] for item in local)]

    @staticmethod
    def _event_id(timeline_id: str, sequence: int, event: NewEvent) -> str:
        canonical = json.dumps(
            event.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(f"{timeline_id}:{sequence}:{canonical}".encode()).hexdigest()
        return f"evt_{digest[:24]}"
