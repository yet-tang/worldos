from __future__ import annotations

from typing import Any


MIN_SCARCITY_TICKS = 3
TRIGGER_SCORE = 85.0


def conflict_propensity(
    *,
    pressure: int,
    hunger: int,
    shortage: int,
    scarcity_ticks: int,
    rumor_pressure: int,
    relationship: int,
    own_food: int,
    target_food: int,
    conflict_caution: int,
    alternative_sellers: int,
    target_avoided: bool,
) -> dict[str, Any]:
    """Return a deterministic, auditable propensity for scarcity-driven conflict.

    Escalation requires both sustained scarcity and a high multi-factor score. This
    preserves the social meaning of a crisis building over time while still allowing
    learned caution, viable market alternatives, and positive relationships to keep a
    severe but marginal situation below the escalation boundary.
    """

    pressure_drive = max(0.0, min(35.0, (int(pressure) - 50) * 0.7))
    hunger_drive = max(0.0, min(15.0, (int(hunger) - 45) * 0.3))
    shortage_drive = max(0.0, min(18.0, int(shortage) * 4.5))
    duration_drive = max(0.0, min(15.0, max(0, int(scarcity_ticks) - 1) * 2.5))
    rumor_drive = max(0.0, min(10.0, int(rumor_pressure) * 3.0))
    grievance_drive = max(0.0, min(18.0, -int(relationship) * 0.3))
    inequality_drive = max(0.0, min(16.0, (int(target_food) - int(own_food)) * 2.0))
    avoidance_drive = 6.0 if target_avoided else 0.0

    caution_brake = max(0.0, min(25.0, float(conflict_caution)))
    alternatives_brake = max(0.0, min(18.0, int(alternative_sellers) * 6.0))
    relationship_brake = max(0.0, min(12.0, int(relationship) * 0.2))

    positive = (
        pressure_drive
        + hunger_drive
        + shortage_drive
        + duration_drive
        + rumor_drive
        + grievance_drive
        + inequality_drive
        + avoidance_drive
    )
    brakes = caution_brake + alternatives_brake + relationship_brake
    score = max(0.0, min(100.0, positive - brakes))
    sustained = int(scarcity_ticks) >= MIN_SCARCITY_TICKS

    return {
        "score": round(score, 3),
        "trigger_score": TRIGGER_SCORE,
        "triggered": sustained and score >= TRIGGER_SCORE,
        "drivers": {
            "pressure": round(pressure_drive, 3),
            "hunger": round(hunger_drive, 3),
            "shortage": round(shortage_drive, 3),
            "scarcity_duration": round(duration_drive, 3),
            "rumor_pressure": round(rumor_drive, 3),
            "grievance": round(grievance_drive, 3),
            "relative_inequality": round(inequality_drive, 3),
            "target_avoidance": round(avoidance_drive, 3),
        },
        "brakes": {
            "adaptive_caution": round(caution_brake, 3),
            "market_alternatives": round(alternatives_brake, 3),
            "positive_relationship": round(relationship_brake, 3),
        },
        "inputs": {
            "pressure": int(pressure),
            "hunger": int(hunger),
            "shortage": int(shortage),
            "scarcity_ticks": int(scarcity_ticks),
            "minimum_scarcity_ticks": MIN_SCARCITY_TICKS,
            "relationship": int(relationship),
            "rumor_pressure": int(rumor_pressure),
            "own_food": int(own_food),
            "target_food": int(target_food),
            "conflict_caution": int(conflict_caution),
            "alternative_sellers": int(alternative_sellers),
            "target_avoided": bool(target_avoided),
        },
    }
