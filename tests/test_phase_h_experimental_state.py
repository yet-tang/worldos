from worldos_core.experimental_state import (
    PHYSICAL_COMPONENT_ALLOWLIST,
    build_physical_override_events,
    capture_experimental_checkpoint,
    pre_treatment_equivalence,
)
from worldos_core.events import Event
from worldos_core.world import EntityProjection, WorldProjection, reduce_event


def world(*, food: int, wallet: int, reserve_bonus: int, seed: str = "phase-h") -> WorldProjection:
    return WorldProjection(
        tick=12,
        flags={"seed": seed},
        entities={
            "人物-001": EntityProjection(
                entity_id="人物-001",
                kind="character",
                components={
                    "inventory": {"food": food},
                    "wallet": wallet,
                    "health": {"current": 90, "maximum": 100},
                    "needs": {"hunger": 25, "fatigue": 10},
                    "survival": {"hunger": 25, "fatigue": 10},
                    "position": {"location_id": "集市"},
                    "food_security": {"food": food, "target_reserve": 5, "shortage": max(0, 5-food), "pressure": 20},
                    "adaptive_strategy": {"reserve_bonus": reserve_bonus},
                },
            )
        },
    )


def materialize(events, *, timeline_id: str = "experiment"):
    return [
        Event(
            sequence=index,
            event_id=f"override-{index}",
            timeline_id=timeline_id,
            tick=event.tick,
            phase=event.phase,
            event_type=event.event_type,
            schema_version=event.schema_version,
            actor_id=event.actor_id,
            subject_ids=event.subject_ids,
            payload=event.payload,
            metadata=event.metadata,
        )
        for index, event in enumerate(events, 1)
    ]


def test_checkpoint_captures_only_physical_allowlist_and_has_stable_digest():
    source = world(food=9, wallet=14, reserve_bonus=6)
    first = capture_experimental_checkpoint(source, timeline_id="experienced", source_sequence=123)
    second = capture_experimental_checkpoint(source, timeline_id="experienced", source_sequence=123)
    assert first.physical_state_digest == second.physical_state_digest
    assert first.source_world_hash == source.canonical_hash()
    assert set(first.component_names) == PHYSICAL_COMPONENT_ALLOWLIST
    assert "adaptive_strategy" not in first.actors[0].components


def test_checkpoint_rejects_experiential_components():
    source = world(food=9, wallet=14, reserve_bonus=6)
    try:
        capture_experimental_checkpoint(source, timeline_id="main", source_sequence=1, component_names=["inventory", "adaptive_strategy"])
    except ValueError as exc:
        assert "adaptive_strategy" in str(exc)
    else:
        raise AssertionError("adaptive_strategy must not be accepted as a physical component")


def test_override_equalizes_physical_state_without_overwriting_strategy():
    source = world(food=9, wallet=14, reserve_bonus=6)
    treatment = world(food=1, wallet=2, reserve_bonus=6)
    control = world(food=3, wallet=7, reserve_bonus=0)
    checkpoint = capture_experimental_checkpoint(source, timeline_id="checkpoint", source_sequence=99)

    treatment_events = build_physical_override_events(treatment, checkpoint, tick=13)
    control_events = build_physical_override_events(control, checkpoint, tick=13)

    for event in materialize(treatment_events, timeline_id="treatment"):
        treatment = reduce_event(treatment, event)
    for event in materialize(control_events, timeline_id="control"):
        control = reduce_event(control, event)

    result = pre_treatment_equivalence(treatment, control)
    assert result["physical_state_equal"] is True
    assert result["seed_equal"] is True
    assert treatment.entities["人物-001"].components["adaptive_strategy"]["reserve_bonus"] == 6
    assert control.entities["人物-001"].components["adaptive_strategy"]["reserve_bonus"] == 0


def test_override_events_are_minimal_deterministic_and_auditable():
    source = world(food=9, wallet=14, reserve_bonus=6)
    target = world(food=1, wallet=14, reserve_bonus=0)
    checkpoint = capture_experimental_checkpoint(source, timeline_id="main", source_sequence=55)
    first = build_physical_override_events(target, checkpoint, tick=20)
    second = build_physical_override_events(target, checkpoint, tick=20)
    assert [event.model_dump(mode="json") for event in first] == [event.model_dump(mode="json") for event in second]
    assert {event.payload["component"] for event in first} == {"inventory", "food_security"}
    assert all(event.payload["experimental_override"] is True for event in first)
    assert all(event.payload["checkpoint_digest"] == checkpoint.physical_state_digest for event in first)


def test_equivalence_detects_physical_difference_even_when_seed_matches():
    treatment = world(food=8, wallet=10, reserve_bonus=6)
    control = world(food=7, wallet=10, reserve_bonus=0)
    result = pre_treatment_equivalence(treatment, control)
    assert result["seed_equal"] is True
    assert result["physical_state_equal"] is False
