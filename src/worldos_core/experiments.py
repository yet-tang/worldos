from __future__ import annotations

from typing import Any


def _actor_index(probe: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(actor.get("actor_id")): actor for actor in probe.get("actors", []) if actor.get("actor_id")}


def compare_probes(control: dict[str, Any], experiment: dict[str, Any]) -> dict[str, Any]:
    """Compare two timeline probes without mutating either timeline."""
    control_world = control.get("world", {})
    experiment_world = experiment.get("world", {})
    ca = _actor_index(control)
    ea = _actor_index(experiment)
    actor_ids = sorted(set(ca) | set(ea))
    actor_changes = []
    for actor_id in actor_ids:
        left, right = ca.get(actor_id, {}), ea.get(actor_id, {})
        if left != right:
            actor_changes.append({"actor_id": actor_id, "control": left, "experiment": right})
    return {
        "control": {
            "timeline": control_world.get("timeline_id", "main"),
            "tick": control_world.get("current_tick"),
            "event_count": control_world.get("event_count"),
            "world_hash": control_world.get("world_hash"),
        },
        "experiment": {
            "timeline": experiment_world.get("timeline_id"),
            "tick": experiment_world.get("current_tick"),
            "event_count": experiment_world.get("event_count"),
            "world_hash": experiment_world.get("world_hash"),
        },
        "delta": {
            "tick": (experiment_world.get("current_tick") or 0) - (control_world.get("current_tick") or 0),
            "events": (experiment_world.get("event_count") or 0) - (control_world.get("event_count") or 0),
            "actor_changes": actor_changes,
            "actor_change_count": len(actor_changes),
        },
    }
