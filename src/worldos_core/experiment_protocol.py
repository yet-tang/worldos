from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Iterable

from pydantic import BaseModel

from .events import Event
from .experimental_state import PHYSICAL_COMPONENT_ALLOWLIST, pre_treatment_equivalence
from .experiments import compare_probes
from .world import WorldProjection, replay_world


@dataclass(frozen=True)
class ExperimentArm:
    name: str
    timeline_id: str
    declared_intervention: dict[str, Any]


@dataclass(frozen=True)
class ExperimentProtocol:
    checkpoint_digest: str
    treatment: ExperimentArm
    control: ExperimentArm
    actor_ids: tuple[str, ...] = ()
    component_names: tuple[str, ...] = tuple(sorted(PHYSICAL_COMPONENT_ALLOWLIST))


class PreTreatmentAttestation(BaseModel):
    """Deterministic pointer to a validated historical pre-treatment state.

    The attestation is not trusted merely because the caller presents it. Post-hoc
    verification replays each timeline at the recorded event-count cutoff and checks
    the attested hashes/equivalence against immutable event history.
    """

    checkpoint_digest: str
    treatment_timeline: str
    control_timeline: str
    treatment_event_count: int
    control_event_count: int
    treatment_world_hash: str
    control_world_hash: str
    treatment_physical_digest: str
    control_physical_digest: str
    treatment_seed: Any = None
    control_seed: Any = None
    treatment_intervention: dict[str, Any]
    control_intervention: dict[str, Any]
    actor_ids: tuple[str, ...] = ()
    component_names: tuple[str, ...] = tuple(sorted(PHYSICAL_COMPONENT_ALLOWLIST))
    valid_for_causal_run: bool
    attestation_digest: str = ""


def _attestation_digest(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _digest_attestation(attestation: PreTreatmentAttestation) -> str:
    payload = attestation.model_dump(mode="json")
    payload.pop("attestation_digest", None)
    return _attestation_digest(payload)


def validate_pre_treatment(
    protocol: ExperimentProtocol,
    treatment_world: WorldProjection,
    control_world: WorldProjection,
) -> dict[str, Any]:
    """Validate the causal preconditions before treatment/stimulus execution.

    A protocol is valid only when selected physical state and deterministic seed match.
    Different declared interventions are intentional; any physical difference is not.
    """

    result = pre_treatment_equivalence(
        treatment_world,
        control_world,
        actor_ids=protocol.actor_ids or None,
        component_names=protocol.component_names,
    )
    treatment_intervention = dict(protocol.treatment.declared_intervention)
    control_intervention = dict(protocol.control.declared_intervention)
    intentional = treatment_intervention != control_intervention
    valid = bool(result["physical_state_equal"] and result["seed_equal"] and intentional)
    return {
        **result,
        "checkpoint_digest": protocol.checkpoint_digest,
        "treatment_timeline": protocol.treatment.timeline_id,
        "control_timeline": protocol.control.timeline_id,
        "treatment_intervention": treatment_intervention,
        "control_intervention": control_intervention,
        "intentional_intervention_difference": intentional,
        "valid_for_causal_run": valid,
    }


def attest_pre_treatment(
    protocol: ExperimentProtocol,
    treatment_world: WorldProjection,
    control_world: WorldProjection,
    *,
    treatment_event_count: int,
    control_event_count: int,
) -> PreTreatmentAttestation:
    pre = validate_pre_treatment(protocol, treatment_world, control_world)
    attestation = PreTreatmentAttestation(
        checkpoint_digest=protocol.checkpoint_digest,
        treatment_timeline=protocol.treatment.timeline_id,
        control_timeline=protocol.control.timeline_id,
        treatment_event_count=int(treatment_event_count),
        control_event_count=int(control_event_count),
        treatment_world_hash=treatment_world.canonical_hash(),
        control_world_hash=control_world.canonical_hash(),
        treatment_physical_digest=str(pre["treatment_physical_digest"]),
        control_physical_digest=str(pre["control_physical_digest"]),
        treatment_seed=pre.get("treatment_seed"),
        control_seed=pre.get("control_seed"),
        treatment_intervention=dict(protocol.treatment.declared_intervention),
        control_intervention=dict(protocol.control.declared_intervention),
        actor_ids=protocol.actor_ids,
        component_names=protocol.component_names,
        valid_for_causal_run=bool(pre["valid_for_causal_run"]),
    )
    return attestation.model_copy(update={"attestation_digest": _digest_attestation(attestation)})


def verify_pre_treatment_attestation(
    protocol: ExperimentProtocol,
    attestation: PreTreatmentAttestation,
    *,
    treatment_history: tuple[Event, ...],
    control_history: tuple[Event, ...],
) -> dict[str, Any]:
    """Verify an attestation against immutable historical event prefixes.

    This makes post-outcome reporting safe: current branch state may have diverged, but
    the pre-treatment eligibility decision can be recomputed at the exact recorded
    historical cutoffs.
    """

    reasons: list[str] = []
    if attestation.attestation_digest != _digest_attestation(attestation):
        reasons.append("attestation digest mismatch")
    if attestation.checkpoint_digest != protocol.checkpoint_digest:
        reasons.append("checkpoint digest mismatch")
    if attestation.treatment_timeline != protocol.treatment.timeline_id:
        reasons.append("treatment timeline mismatch")
    if attestation.control_timeline != protocol.control.timeline_id:
        reasons.append("control timeline mismatch")
    if attestation.treatment_intervention != dict(protocol.treatment.declared_intervention):
        reasons.append("treatment intervention mismatch")
    if attestation.control_intervention != dict(protocol.control.declared_intervention):
        reasons.append("control intervention mismatch")
    if tuple(attestation.actor_ids) != tuple(protocol.actor_ids):
        reasons.append("actor selection mismatch")
    if tuple(attestation.component_names) != tuple(protocol.component_names):
        reasons.append("component selection mismatch")

    if not (0 < attestation.treatment_event_count <= len(treatment_history)):
        reasons.append("treatment event cutoff unavailable")
    if not (0 < attestation.control_event_count <= len(control_history)):
        reasons.append("control event cutoff unavailable")

    if reasons:
        return {
            "valid_for_causal_run": False,
            "attestation_verified": False,
            "attestation_digest": attestation.attestation_digest,
            "verification_errors": reasons,
        }

    treatment_world = replay_world(treatment_history[: attestation.treatment_event_count])
    control_world = replay_world(control_history[: attestation.control_event_count])
    recomputed = validate_pre_treatment(protocol, treatment_world, control_world)

    if treatment_world.canonical_hash() != attestation.treatment_world_hash:
        reasons.append("treatment historical hash mismatch")
    if control_world.canonical_hash() != attestation.control_world_hash:
        reasons.append("control historical hash mismatch")
    if recomputed.get("treatment_physical_digest") != attestation.treatment_physical_digest:
        reasons.append("treatment physical digest mismatch")
    if recomputed.get("control_physical_digest") != attestation.control_physical_digest:
        reasons.append("control physical digest mismatch")
    if recomputed.get("treatment_seed") != attestation.treatment_seed:
        reasons.append("treatment seed mismatch")
    if recomputed.get("control_seed") != attestation.control_seed:
        reasons.append("control seed mismatch")
    if bool(recomputed.get("valid_for_causal_run")) != bool(attestation.valid_for_causal_run):
        reasons.append("attested eligibility mismatch")

    verified = not reasons and bool(attestation.valid_for_causal_run)
    return {
        **recomputed,
        "valid_for_causal_run": verified,
        "attestation_verified": verified,
        "attestation_digest": attestation.attestation_digest,
        "attested_treatment_event_count": attestation.treatment_event_count,
        "attested_control_event_count": attestation.control_event_count,
        "verification_errors": reasons,
    }


def causal_report(
    protocol: ExperimentProtocol,
    *,
    pre_treatment: dict[str, Any],
    treatment_probe: dict[str, Any],
    control_probe: dict[str, Any],
    outcome_names: Iterable[str] = (),
) -> dict[str, Any]:
    """Produce an attribution-oriented report from two already executed branches.

    This function does not claim causality if the pre-treatment equivalence check failed.
    It carries the declared treatment difference alongside ordinary timeline deltas so
    downstream tools cannot silently turn an observational comparison into a causal one.
    """

    comparison = compare_probes(control_probe, treatment_probe)
    selected_outcomes: dict[str, Any] = {}
    metrics = comparison.get("delta", {}).get("metrics", {})
    for name in outcome_names:
        if name in metrics:
            selected_outcomes[name] = metrics[name]

    attributable = bool(pre_treatment.get("valid_for_causal_run"))
    return {
        "protocol": {
            "checkpoint_digest": protocol.checkpoint_digest,
            "treatment": {
                "name": protocol.treatment.name,
                "timeline_id": protocol.treatment.timeline_id,
                "intervention": dict(protocol.treatment.declared_intervention),
            },
            "control": {
                "name": protocol.control.name,
                "timeline_id": protocol.control.timeline_id,
                "intervention": dict(protocol.control.declared_intervention),
            },
        },
        "pre_treatment_equivalence": pre_treatment,
        "comparison": comparison,
        "selected_outcomes": selected_outcomes,
        "attribution": {
            "eligible": attributable,
            "declared_difference": (
                {
                    "treatment": dict(protocol.treatment.declared_intervention),
                    "control": dict(protocol.control.declared_intervention),
                }
                if attributable
                else None
            ),
            "reason": (
                "declared intervention under verified equivalent historical physical state and deterministic seed"
                if attributable and pre_treatment.get("attestation_verified")
                else (
                    "declared intervention under equivalent physical state and deterministic seed"
                    if attributable
                    else "pre-treatment equivalence requirements not satisfied"
                )
            ),
        },
    }
