from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .experimental_state import PHYSICAL_COMPONENT_ALLOWLIST, pre_treatment_equivalence
from .experiments import compare_probes
from .world import WorldProjection


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
                "declared intervention under equivalent physical state and deterministic seed"
                if attributable
                else "pre-treatment equivalence requirements not satisfied"
            ),
        },
    }
