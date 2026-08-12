from __future__ import annotations

from worldos_core.adaptive import AdaptiveMemoryModule


def _memory(event_type: str, tick: int, salience: float = 0.7, other: str | None = None):
    subject_ids = ["a"] + ([other] if other else [])
    return {
        "content": {
            "experience_type": event_type,
            "subject_ids": subject_ids,
            "payload": {},
        },
        "recorded_tick": tick,
        "salience": salience,
        "confidence": 1.0,
    }


def test_isolated_old_memory_decays_but_never_disappears() -> None:
    recent = _memory("scarcity.perceived", 190)
    old = _memory("scarcity.perceived", 0)
    recent_strength = AdaptiveMemoryModule._memory_strength(recent, current_tick=200, repetition_count=1)
    old_strength = AdaptiveMemoryModule._memory_strength(old, current_tick=200, repetition_count=1)
    assert recent_strength > old_strength > 0


def test_repetition_reinforces_same_age_experience() -> None:
    memory = _memory("scarcity.perceived", 100)
    one = AdaptiveMemoryModule._memory_strength(memory, current_tick=110, repetition_count=1)
    repeated = AdaptiveMemoryModule._memory_strength(memory, current_tick=110, repetition_count=8)
    assert repeated > one


def test_repeated_recent_scarcity_builds_more_reserve_than_old_isolated_history() -> None:
    recent = [_memory("scarcity.perceived", 95 + index) for index in range(6)]
    old = [_memory("scarcity.perceived", 0)]
    recent_strategy = AdaptiveMemoryModule._strategy("a", recent, current_tick=105)
    old_strategy = AdaptiveMemoryModule._strategy("a", old, current_tick=205)
    assert recent_strategy["reserve_bonus"] > old_strategy["reserve_bonus"]
    assert recent_strategy["evidence"]["effective_scarcity_exposure"] > old_strategy["evidence"]["effective_scarcity_exposure"]


def test_partner_preference_can_fade_when_only_supported_by_old_memory() -> None:
    recent = [_memory("trade.completed", 99, 0.8, "b")]
    old = [_memory("trade.completed", 0, 0.8, "b")]
    recent_strategy = AdaptiveMemoryModule._strategy("a", recent, current_tick=100)
    old_strategy = AdaptiveMemoryModule._strategy("a", old, current_tick=300)
    assert "b" in recent_strategy["preferred_partners"]
    assert "b" not in old_strategy["preferred_partners"]
