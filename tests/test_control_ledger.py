from pathlib import Path

import pytest

from worldos_core.control_ledger import (
    CommandKeyConflict,
    CommandOutcomeUnknown,
    ControlCommandLedger,
)


def test_control_ledger_replays_completed_command_after_restart(tmp_path: Path) -> None:
    path = tmp_path / "control_commands.db"
    request_hash = ControlCommandLedger.fingerprint(
        "POST", "/api/control/worlds/a/advance", {"ticks": 1, "idempotency_key": "k1"}
    )

    with ControlCommandLedger(path) as ledger:
        assert ledger.reserve("k1", request_hash, method="POST", path="/api/control/worlds/a/advance") is None
        ledger.complete("k1", status_code=200, response={"after_tick": 1})

    with ControlCommandLedger(path) as ledger:
        replay = ledger.reserve("k1", request_hash, method="POST", path="/api/control/worlds/a/advance")
        assert replay is not None
        assert replay.status_code == 200
        assert replay.response == {"after_tick": 1}


def test_control_ledger_fails_closed_for_ambiguous_reserved_command(tmp_path: Path) -> None:
    path = tmp_path / "control_commands.db"
    request_hash = ControlCommandLedger.fingerprint(
        "POST", "/api/control/worlds/a/advance", {"ticks": 100, "idempotency_key": "ambiguous"}
    )

    with ControlCommandLedger(path) as ledger:
        assert ledger.reserve(
            "ambiguous",
            request_hash,
            method="POST",
            path="/api/control/worlds/a/advance",
        ) is None
        # Simulate process death before ledger.complete().

    with ControlCommandLedger(path) as ledger:
        with pytest.raises(CommandOutcomeUnknown):
            ledger.reserve(
                "ambiguous",
                request_hash,
                method="POST",
                path="/api/control/worlds/a/advance",
            )
        command = ledger.get("ambiguous")
        assert command is not None
        assert command["state"] == "in_progress"


def test_control_ledger_rejects_key_reuse_with_different_request(tmp_path: Path) -> None:
    path = tmp_path / "control_commands.db"
    first = ControlCommandLedger.fingerprint("POST", "/x", {"ticks": 1})
    second = ControlCommandLedger.fingerprint("POST", "/x", {"ticks": 2})

    with ControlCommandLedger(path) as ledger:
        ledger.reserve("same-key", first, method="POST", path="/x")
        ledger.complete("same-key", status_code=200, response={"ok": True})
        with pytest.raises(CommandKeyConflict):
            ledger.reserve("same-key", second, method="POST", path="/x")
