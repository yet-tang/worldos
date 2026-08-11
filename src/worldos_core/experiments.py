from __future__ import annotations

from typing import Any


def _actor_index(probe: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(actor.get("actor_id")): actor for actor in probe.get("actors", []) if actor.get("actor_id")}


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def outcome_metrics(probe: dict[str, Any]) -> dict[str, Any]:
    actors = list(probe.get("actors", []))
    hunger: list[float] = []
    fatigue: list[float] = []
    health: list[float] = []
    wealth = 0.0
    inventories: dict[str, float] = {}
    rumor_holders = 0
    for actor in actors:
        needs = actor.get("needs", {}) if isinstance(actor.get("needs", {}), dict) else {}
        health_state = actor.get("health", {}) if isinstance(actor.get("health", {}), dict) else {}
        hunger.append(_number(needs.get("hunger")))
        fatigue.append(_number(needs.get("fatigue")))
        health.append(_number(health_state.get("current", 100)))
        wealth += _number(actor.get("wallet"))
        inventory = actor.get("inventory", {}) if isinstance(actor.get("inventory", {}), dict) else {}
        for resource, quantity in inventory.items():
            inventories[str(resource)] = inventories.get(str(resource), 0.0) + _number(quantity)
        if actor.get("rumors"):
            rumor_holders += 1
    counts: dict[str, int] = {}
    for event in probe.get("recent_events", []):
        event_type = str(event.get("event_type", "")) if isinstance(event, dict) else ""
        counts[event_type] = counts.get(event_type, 0) + 1
    avg = lambda values: (sum(values) / len(values)) if values else 0.0
    return {
        "actor_count": len(actors),
        "average_hunger": round(avg(hunger), 3),
        "average_fatigue": round(avg(fatigue), 3),
        "average_health": round(avg(health), 3),
        "total_wealth": round(wealth, 3),
        "inventory_totals": dict(sorted(inventories.items())),
        "rumor_holders": rumor_holders,
        "recent_trade_events": counts.get("trade.completed", 0),
        "recent_conflict_events": counts.get("conflict.resolved", 0),
        "recent_rumor_events": counts.get("rumor.spread", 0),
        "recent_production_events": counts.get("resource.produced", 0),
    }


def _metric_delta(control: dict[str, Any], experiment: dict[str, Any]) -> dict[str, Any]:
    delta: dict[str, Any] = {}
    for key in sorted(set(control) | set(experiment)):
        left, right = control.get(key), experiment.get(key)
        if isinstance(left, (int, float)) and isinstance(right, (int, float)):
            delta[key] = round(float(right) - float(left), 3)
        elif isinstance(left, dict) and isinstance(right, dict):
            delta[key] = {name: round(_number(right.get(name)) - _number(left.get(name)), 3) for name in sorted(set(left) | set(right))}
    return delta


def compare_probes(control: dict[str, Any], experiment: dict[str, Any]) -> dict[str, Any]:
    """Compare two real WorldReadService probes without mutating either timeline."""
    control_snapshot = control.get("snapshot", {})
    experiment_snapshot = experiment.get("snapshot", {})
    ca = _actor_index(control)
    ea = _actor_index(experiment)
    actor_changes = []
    for actor_id in sorted(set(ca) | set(ea)):
        left, right = ca.get(actor_id, {}), ea.get(actor_id, {})
        if left != right:
            actor_changes.append({"actor_id": actor_id, "control": left, "experiment": right})
    control_metrics = outcome_metrics(control)
    experiment_metrics = outcome_metrics(experiment)
    return {
        "control": {
            "timeline": control_snapshot.get("timeline_id", "main"),
            "tick": control_snapshot.get("current_tick"),
            "event_count": control_snapshot.get("event_count"),
            "world_hash": control_snapshot.get("world_hash"),
            "metrics": control_metrics,
        },
        "experiment": {
            "timeline": experiment_snapshot.get("timeline_id"),
            "tick": experiment_snapshot.get("current_tick"),
            "event_count": experiment_snapshot.get("event_count"),
            "world_hash": experiment_snapshot.get("world_hash"),
            "metrics": experiment_metrics,
        },
        "delta": {
            "tick": (experiment_snapshot.get("current_tick") or 0) - (control_snapshot.get("current_tick") or 0),
            "events": (experiment_snapshot.get("event_count") or 0) - (control_snapshot.get("event_count") or 0),
            "metrics": _metric_delta(control_metrics, experiment_metrics),
            "actor_changes": actor_changes,
            "actor_change_count": len(actor_changes),
        },
    }
