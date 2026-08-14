from __future__ import annotations

from typing import Any

from .adaptive import AdaptiveMemoryModule
from .events import Event


def effective_memory_view(
    history: tuple[Event, ...],
    *,
    actor_id: str,
    current_tick: int,
) -> dict[str, Any]:
    """Project branch-local memory treatments without advancing the world.

    Adaptive strategy is normally persisted during the next module tick. Experiment
    tooling needs to inspect the effective treatment immediately after an intervention,
    so this read model derives the same strategy and per-memory strengths directly from
    immutable history at the current tick.
    """

    memories = AdaptiveMemoryModule._experience_memories(history).get(actor_id, [])
    raw_counts: dict[str, int] = {}
    for memory in memories:
        content = memory.get("content", memory)
        experience_type = str(content.get("experience_type") or "")
        raw_counts[experience_type] = raw_counts.get(experience_type, 0) + 1

    effective: list[dict[str, Any]] = []
    for memory in memories:
        content = memory.get("content", memory)
        experience_type = str(content.get("experience_type") or "")
        strength = AdaptiveMemoryModule._memory_strength(
            memory,
            current_tick=current_tick,
            repetition_count=raw_counts.get(experience_type, 1),
        )
        effective.append(
            {
                "memory_id": memory.get("memory_id"),
                "experience_type": experience_type,
                "recorded_tick": memory.get("recorded_tick"),
                "effective_strength": strength,
                "treatment_multiplier": memory.get("treatment_multiplier", 1.0),
                "intervention_event_ids": list(memory.get("intervention_event_ids", ())),
                "replaced": bool(memory.get("replaced")),
                "content": content,
            }
        )

    strategy = AdaptiveMemoryModule._strategy(
        actor_id,
        memories,
        current_tick=current_tick,
    )
    return {
        "actor_id": actor_id,
        "current_tick": current_tick,
        "effective_memory_count": len(effective),
        "effective_memories": effective,
        "effective_strategy": strategy,
    }
