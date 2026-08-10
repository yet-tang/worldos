from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any


@dataclass(frozen=True)
class CommandReplay:
    status_code: int
    response: dict[str, Any]


class CommandKeyConflict(RuntimeError):
    pass


class CommandOutcomeUnknown(RuntimeError):
    pass


class ControlCommandLedger:
    """Persistent idempotency ledger for remote control mutations.

    The ledger intentionally lives outside individual world databases so create/delete
    commands remain replayable even when the target world does not (or no longer) exists.
    A command is reserved durably before its side effect. If the process dies after the
    reservation but before recording the response, retries fail closed with
    CommandOutcomeUnknown rather than executing the mutation twice.
    """

    SCHEMA_VERSION = 1

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=FULL")
        self.connection.execute("PRAGMA busy_timeout=30000")
        self._migrate()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "ControlCommandLedger":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    @staticmethod
    def fingerprint(
        method: str,
        path: str,
        payload: dict[str, Any] | None,
        *,
        if_match: str | None = None,
    ) -> str:
        canonical_payload = dict(payload or {})
        canonical_payload.pop("idempotency_key", None)
        document = {
            "method": method.upper(),
            "path": path,
            "payload": canonical_payload,
            "if_match": if_match or "",
        }
        canonical = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def reserve(
        self,
        idempotency_key: str,
        request_hash: str,
        *,
        method: str,
        path: str,
    ) -> CommandReplay | None:
        if not idempotency_key:
            raise ValueError("idempotency_key is required for mutations")
        if len(idempotency_key) > 200:
            raise ValueError("idempotency_key is too long")

        self.connection.execute("BEGIN IMMEDIATE")
        try:
            row = self.connection.execute(
                "SELECT request_hash, state, status_code, response_json FROM control_commands WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if row is not None:
                if row["request_hash"] != request_hash:
                    raise CommandKeyConflict(
                        "idempotency_key was already used for a different command"
                    )
                if row["state"] == "completed":
                    response = json.loads(row["response_json"] or "{}")
                    self.connection.execute("COMMIT")
                    return CommandReplay(int(row["status_code"]), response)
                raise CommandOutcomeUnknown(
                    "command is already reserved and its outcome is not safely replayable"
                )

            now = datetime.now(UTC).isoformat()
            self.connection.execute(
                """
                INSERT INTO control_commands(
                    idempotency_key, request_hash, method, path, state, created_at
                ) VALUES (?, ?, ?, ?, 'in_progress', ?)
                """,
                (idempotency_key, request_hash, method.upper(), path, now),
            )
            self.connection.execute("COMMIT")
            return None
        except Exception:
            if self.connection.in_transaction:
                self.connection.execute("ROLLBACK")
            raise

    def complete(
        self,
        idempotency_key: str,
        *,
        status_code: int,
        response: dict[str, Any],
    ) -> None:
        document = json.dumps(response, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        completed_at = datetime.now(UTC).isoformat()
        cursor = self.connection.execute(
            """
            UPDATE control_commands
            SET state = 'completed', status_code = ?, response_json = ?, completed_at = ?
            WHERE idempotency_key = ? AND state = 'in_progress'
            """,
            (status_code, document, completed_at, idempotency_key),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("control command reservation disappeared before completion")

    def release(self, idempotency_key: str) -> None:
        """Release a reservation only when no side effect was committed.

        Callers must never release after a mutation may have happened. Ambiguous outcomes
        deliberately remain in_progress so a retry cannot duplicate the command.
        """

        self.connection.execute(
            "DELETE FROM control_commands WHERE idempotency_key = ? AND state = 'in_progress'",
            (idempotency_key,),
        )

    def get(self, idempotency_key: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            SELECT idempotency_key, request_hash, method, path, state, status_code,
                   response_json, created_at, completed_at
            FROM control_commands WHERE idempotency_key = ?
            """,
            (idempotency_key,),
        ).fetchone()
        if row is None:
            return None
        return {
            "idempotency_key": row["idempotency_key"],
            "request_hash": row["request_hash"],
            "method": row["method"],
            "path": row["path"],
            "state": row["state"],
            "status_code": row["status_code"],
            "response": json.loads(row["response_json"]) if row["response_json"] else None,
            "created_at": row["created_at"],
            "completed_at": row["completed_at"],
        }

    def _migrate(self) -> None:
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS control_schema_migrations (version INTEGER PRIMARY KEY)"
        )
        current = int(
            self.connection.execute(
                "SELECT COALESCE(MAX(version), 0) FROM control_schema_migrations"
            ).fetchone()[0]
        )
        if current > self.SCHEMA_VERSION:
            raise RuntimeError(
                f"control ledger schema {current} is newer than supported {self.SCHEMA_VERSION}"
            )
        if current == 0:
            self.connection.executescript(
                """
                BEGIN IMMEDIATE;
                CREATE TABLE control_commands (
                    idempotency_key TEXT PRIMARY KEY,
                    request_hash TEXT NOT NULL,
                    method TEXT NOT NULL,
                    path TEXT NOT NULL,
                    state TEXT NOT NULL CHECK(state IN ('in_progress', 'completed')),
                    status_code INTEGER,
                    response_json TEXT,
                    created_at TEXT NOT NULL,
                    completed_at TEXT
                );
                CREATE INDEX control_commands_state_created
                    ON control_commands(state, created_at);
                INSERT INTO control_schema_migrations(version) VALUES (1);
                COMMIT;
                """
            )
