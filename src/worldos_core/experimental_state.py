from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Any, Iterable

from pydantic import BaseModel, Field

from .events import NewEvent
from .world import WorldProjection


PHYSICAL_COMPONENT_ALLOWLIST = frozenset({
    "inventory",
    "wallet",
    "health",
    "needs",
    "survival",
    "position",
    "food_security",
    "production_carry",
})


class ActorPhysicalState(BaseModel):
    actor_id: str
    components: dict[str, Any] = Field(default_factory=dict)


class ExperimentalCheckpoint(BaseModel):
    source_timeline_id: str
    source_sequence: int
    source_tick: int
    source_world_hash: str
    component_names: tuple[str, ...]
    actors: tuple[ActorPhysicalState, ...]
    physical_state_digest: str


def _canonical_digest(payload: Any) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def capture_experimental_checkpoint(
    world: WorldProjection,
    *,
    timeline_id: str,
    source_sequence: int,
    actor_ids: Iterable[str] | None = None,
    component_names: Iterable[str] = PHYSICAL_COMPONENT_ALLOWLIST,
) -> ExperimentalCheckpoint:
    names = tuple(sorted({str(name) for name in component_names}))
    unsupported = sorted(set(names) - PHYSICAL_COMPONENT_ALLOWLIST)
    if unsupported:
        raise ValueError(f"unsupported physical components: {', '.join(unsupported)}")

    selected = sorted(set(actor_ids) if actor_ids is not None else world.entities)
    actors: list[ActorPhysicalState] = []
    for actor_id in selected:
        entity = world.entities.get(actor_id)
        if entity is None:
            raise ValueError(f"unknown entity: {actor_id}")
        if entity.kind != "character":
            continue
        components = {name: deepcopy(entity.components[name]) for name in names if name in entity.components}
        actors.append(ActorPhysicalState(actor_id=actor_id, components=components))

    digest_payload = {
        "component_names": names,
        "actors": [actor.model_dump(mode="json") for actor in actors],
    }
    return ExperimentalCheckpoint(
        source_timeline_id=timeline_id,
        source_sequence=int(source_sequence),
        source_tick=int(world.tick),
        source_world_hash=world.canonical_hash(),
        component_names=names,
        actors=tuple(actors),
        physical_state_digest=_canonical_digest(digest_payload),
    )


def physical_state_digest(
    world: WorldProjection,
    *,
    actor_ids: Iterable[str] | None = None,
    component_names: Iterable[str] = PHYSICAL_COMPONENT_ALLOWLIST,
) -> str:
    return capture_experimental_checkpoint(
        world,
        timeline_id="digest",
        source_sequence=0,
        actor_ids=actor_ids,
        component_names=component_names,
    ).physical_state_digest


def _selected_checkpoint_actors(
    world: WorldProjection,
    checkpoint: ExperimentalCheckpoint,
    actor_ids: Iterable[str] | None,
) -> list[ActorPhysicalState]:
    selected = set(actor_ids) if actor_ids is not None else {actor.actor_id for actor in checkpoint.actors}
    manifest = {actor.actor_id: actor for actor in checkpoint.actors}
    unknown = sorted(selected - set(manifest))
    if unknown:
        raise ValueError(f"actors not present in checkpoint: {', '.join(unknown)}")
    actors: list[ActorPhysicalState] = []
    for actor_id in sorted(selected):
        entity = world.entities.get(actor_id)
        if entity is None:
            raise ValueError(f"unknown entity: {actor_id}")
        if entity.kind != "character":
            raise ValueError(f"physical override requires character entity: {actor_id}")
        actors.append(manifest[actor_id])
    return actors


def build_atomic_physical_override_event(
    world: WorldProjection,
    checkpoint: ExperimentalCheckpoint,
    *,
    tick: int,
    actor_ids: Iterable[str] | None = None,
) -> NewEvent:
    """Compile a checkpoint restore into one event so equalization is atomic.

    The event carries only the physical allowlisted manifest. Experiential components
    such as adaptive_strategy and memories remain untouched by the world reducer.
    """
    actors = _selected_checkpoint_actors(world, checkpoint, actor_ids)
    return NewEvent(
        tick=tick,
        phase="experiment",
        event_type="experiment.physical_state_override",
        subject_ids=tuple(actor.actor_id for actor in actors),
        payload={
            "checkpoint_digest": checkpoint.physical_state_digest,
            "source_timeline_id": checkpoint.source_timeline_id,
            "source_sequence": checkpoint.source_sequence,
            "source_world_hash": checkpoint.source_world_hash,
            "component_names": list(checkpoint.component_names),
            "actors": [actor.model_dump(mode="json") for actor in actors],
        },
    )


def build_physical_override_events(
    world: WorldProjection,
    checkpoint: ExperimentalCheckpoint,
    *,
    tick: int,
    actor_ids: Iterable[str] | None = None,
) -> list[NewEvent]:
    selected_actors = _selected_checkpoint_actors(world, checkpoint, actor_ids)
    events: list[NewEvent] = []
    for actor in selected_actors:
        actor_id = actor.actor_id
        entity = world.entities[actor_id]
        desired = actor.components
        for component in checkpoint.component_names:
            currently_present = component in entity.components
            desired_present = component in desired
            if desired_present:
                desired_value = deepcopy(desired[component])
                if not currently_present or entity.components.get(component) != desired_value:
                    events.append(NewEvent(
                        tick=tick,
                        phase="experiment",
                        event_type="entity.component_set",
                        actor_id=actor_id,
                        subject_ids=(actor_id,),
                        payload={
                            "component": component,
                            "value": desired_value,
                            "experimental_override": True,
                            "checkpoint_digest": checkpoint.physical_state_digest,
                        },
                    ))
            elif currently_present:
                events.append(NewEvent(
                    tick=tick,
                    phase="experiment",
                    event_type="entity.component_removed",
                    actor_id=actor_id,
                    subject_ids=(actor_id,),
                    payload={
                        "component": component,
                        "experimental_override": True,
                        "checkpoint_digest": checkpoint.physical_state_digest,
                    },
                ))
    return events


def pre_treatment_equivalence(
    treatment: WorldProjection,
    control: WorldProjection,
    *,
    actor_ids: Iterable[str] | None = None,
    component_names: Iterable[str] = PHYSICAL_COMPONENT_ALLOWLIST,
) -> dict[str, Any]:
    left = physical_state_digest(treatment, actor_ids=actor_ids, component_names=component_names)
    right = physical_state_digest(control, actor_ids=actor_ids, component_names=component_names)
    return {
        "physical_state_equal": left == right,
        "treatment_physical_digest": left,
        "control_physical_digest": right,
        "seed_equal": treatment.flags.get("seed") == control.flags.get("seed"),
        "treatment_seed": treatment.flags.get("seed"),
        "control_seed": control.flags.get("seed"),
    }
