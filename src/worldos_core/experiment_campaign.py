from __future__ import annotations

import hashlib
import json
import statistics
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class CampaignTrialPlan(BaseModel):
    trial_id: str
    seed: str
    ordinal: int


class ExperimentCampaignPlan(BaseModel):
    campaign_name: str
    base_seed: str
    trial_count: int
    protocol_template: dict[str, Any] = Field(default_factory=dict)
    campaign_id: str
    trials: tuple[CampaignTrialPlan, ...]


class CampaignTrialResult(BaseModel):
    trial_id: str
    seed: str
    attestation_digest: str = ""
    attribution_eligible: bool
    attestation_verified: bool
    protocol_match: bool = True
    protocol_fingerprint: str = ""
    outcomes: dict[str, float] = Field(default_factory=dict)
    behavioral_outcomes: dict[str, float] = Field(default_factory=dict)
    rejection_reason: str | None = None
    source_fingerprint: str = ""

    @field_validator("outcomes", "behavioral_outcomes")
    @classmethod
    def finite_metrics(cls, value: dict[str, float]) -> dict[str, float]:
        result: dict[str, float] = {}
        for key, item in value.items():
            numeric = float(item)
            if numeric != numeric or numeric in {float("inf"), float("-inf")}:
                raise ValueError(f"metric {key} must be finite")
            result[str(key)] = numeric
        return result

    @model_validator(mode="after")
    def eligible_trials_require_auditable_evidence(self) -> "CampaignTrialResult":
        if self.attribution_eligible and self.attestation_verified and self.protocol_match:
            if not self.attestation_digest.strip():
                raise ValueError("causally eligible trial requires attestation_digest")
            if not self.source_fingerprint.strip():
                raise ValueError("causally eligible trial requires source_fingerprint")
        return self


class MetricReplicationSummary(BaseModel):
    metric: str
    sample_count: int
    mean: float
    median: float
    minimum: float
    maximum: float
    sample_stddev: float
    positive_count: int
    negative_count: int
    zero_count: int
    dominant_sign: str
    sign_consistency: float
    values: tuple[float, ...]


class ExperimentCampaignReport(BaseModel):
    campaign_id: str
    campaign_name: str
    trial_count: int
    eligible_trial_count: int
    rejected_trial_count: int
    eligible_trial_ids: tuple[str, ...]
    rejected_trials: tuple[dict[str, str], ...]
    outcome_metrics: dict[str, MetricReplicationSummary]
    behavioral_metrics: dict[str, MetricReplicationSummary]
    report_fingerprint: str


def _canonical_hash(payload: Any) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _flatten_numeric_metrics(value: Any, *, prefix: str = "") -> dict[str, float]:
    """Flatten numeric leaves from causal-report outcome structures.

    Phase I exposes outcomes such as ``inventory_totals`` as nested dictionaries. A
    replicated campaign needs stable scalar metric names, so nested leaves become dotted
    keys (for example ``inventory_totals.food``). Booleans and non-numeric leaves are
    intentionally ignored rather than coerced.
    """

    result: dict[str, float] = {}
    if isinstance(value, dict):
        for key in sorted(value):
            name = f"{prefix}.{key}" if prefix else str(key)
            result.update(_flatten_numeric_metrics(value[key], prefix=name))
    elif isinstance(value, (int, float)) and not isinstance(value, bool) and prefix:
        result[prefix] = float(value)
    return result


def build_campaign_plan(
    *,
    campaign_name: str,
    base_seed: str,
    trial_count: int,
    protocol_template: dict[str, Any] | None = None,
) -> ExperimentCampaignPlan:
    name = campaign_name.strip()
    seed = base_seed.strip()
    if not name:
        raise ValueError("campaign_name is required")
    if not seed:
        raise ValueError("base_seed is required")
    if trial_count < 2 or trial_count > 100:
        raise ValueError("trial_count must be between 2 and 100")

    protocol = dict(protocol_template or {})
    identity_payload = {
        "campaign_name": name,
        "base_seed": seed,
        "trial_count": int(trial_count),
        "protocol_template": protocol,
    }
    campaign_id = f"campaign-{_canonical_hash(identity_payload)[:16]}"
    trials: list[CampaignTrialPlan] = []
    for ordinal in range(1, trial_count + 1):
        derived = _canonical_hash({"campaign_id": campaign_id, "ordinal": ordinal})
        trials.append(
            CampaignTrialPlan(
                trial_id=f"{campaign_id}-trial-{ordinal:03d}",
                seed=f"{seed}:{derived[:16]}",
                ordinal=ordinal,
            )
        )
    return ExperimentCampaignPlan(
        campaign_name=name,
        base_seed=seed,
        trial_count=trial_count,
        protocol_template=protocol,
        campaign_id=campaign_id,
        trials=tuple(trials),
    )


def _observed_protocol(causal_report: dict[str, Any]) -> dict[str, Any]:
    protocol = causal_report.get("protocol", {}) if isinstance(causal_report, dict) else {}
    treatment = protocol.get("treatment", {}) if isinstance(protocol, dict) else {}
    control = protocol.get("control", {}) if isinstance(protocol, dict) else {}
    selected = causal_report.get("selected_outcomes", {}) if isinstance(causal_report, dict) else {}
    return {
        "treatment_intervention": dict(treatment.get("intervention") or {}) if isinstance(treatment, dict) else {},
        "control_intervention": dict(control.get("intervention") or {}) if isinstance(control, dict) else {},
        "outcome_names": sorted(str(key) for key in selected) if isinstance(selected, dict) else [],
    }


def _normalized_protocol_template(template: dict[str, Any]) -> dict[str, Any]:
    aliases = {
        "treatment": "treatment_intervention",
        "control": "control_intervention",
    }
    normalized: dict[str, Any] = {}
    for key, value in template.items():
        observed_key = aliases.get(key, key)
        if observed_key not in {"treatment_intervention", "control_intervention", "outcome_names"}:
            continue
        if observed_key == "outcome_names":
            normalized[observed_key] = sorted(str(item) for item in value)
        elif isinstance(value, dict):
            normalized[observed_key] = dict(value)
        else:
            normalized[observed_key] = value
    return normalized


def _protocol_matches(template: dict[str, Any], observed: dict[str, Any]) -> bool:
    normalized = _normalized_protocol_template(template)
    if not normalized:
        return True
    for key, expected in normalized.items():
        if observed.get(key) != expected:
            return False
    return True


def trial_result_from_causal_report(
    *,
    trial_id: str,
    seed: str,
    causal_report: dict[str, Any],
    behavioral_outcomes: dict[str, float] | None = None,
    expected_protocol_template: dict[str, Any] | None = None,
) -> CampaignTrialResult:
    attribution = causal_report.get("attribution", {}) if isinstance(causal_report, dict) else {}
    pre = causal_report.get("pre_treatment_equivalence", {}) if isinstance(causal_report, dict) else {}
    selected = causal_report.get("selected_outcomes", {}) if isinstance(causal_report, dict) else {}
    outcomes = _flatten_numeric_metrics(selected if isinstance(selected, dict) else {})

    observed_protocol = _observed_protocol(causal_report)
    protocol_match = _protocol_matches(dict(expected_protocol_template or {}), observed_protocol)
    eligible = bool(attribution.get("eligible"))
    verified = bool(pre.get("attestation_verified"))
    reason = None
    if not protocol_match:
        reason = "trial protocol does not match campaign template"
    elif not eligible or not verified:
        errors = pre.get("verification_errors") if isinstance(pre, dict) else None
        if isinstance(errors, list) and errors:
            reason = "; ".join(str(item) for item in errors)
        else:
            reason = str(attribution.get("reason") or "trial is not causally eligible")

    protocol_fingerprint = _canonical_hash(observed_protocol)
    fingerprint_payload = {
        "trial_id": trial_id,
        "seed": seed,
        "attestation_digest": str(pre.get("attestation_digest") or ""),
        "attribution_eligible": eligible,
        "attestation_verified": verified,
        "protocol_match": protocol_match,
        "protocol_fingerprint": protocol_fingerprint,
        "outcomes": outcomes,
        "behavioral_outcomes": dict(behavioral_outcomes or {}),
    }
    source_fingerprint = _canonical_hash(fingerprint_payload)
    return CampaignTrialResult(
        trial_id=trial_id,
        seed=seed,
        attestation_digest=str(pre.get("attestation_digest") or ""),
        attribution_eligible=eligible,
        attestation_verified=verified,
        protocol_match=protocol_match,
        protocol_fingerprint=protocol_fingerprint,
        outcomes=outcomes,
        behavioral_outcomes=dict(behavioral_outcomes or {}),
        rejection_reason=reason,
        source_fingerprint=source_fingerprint,
    )


def _metric_summary(metric: str, values: list[float]) -> MetricReplicationSummary:
    if not values:
        raise ValueError("metric summary requires at least one value")
    positive = sum(1 for value in values if value > 0)
    negative = sum(1 for value in values if value < 0)
    zero = len(values) - positive - negative
    counts = {"positive": positive, "negative": negative, "zero": zero}
    dominant_count = max(counts.values())
    tied = sorted(sign for sign, count in counts.items() if count == dominant_count)
    dominant_sign = tied[0] if len(tied) == 1 else "mixed"
    return MetricReplicationSummary(
        metric=metric,
        sample_count=len(values),
        mean=round(statistics.fmean(values), 6),
        median=round(statistics.median(values), 6),
        minimum=round(min(values), 6),
        maximum=round(max(values), 6),
        sample_stddev=round(statistics.stdev(values), 6) if len(values) > 1 else 0.0,
        positive_count=positive,
        negative_count=negative,
        zero_count=zero,
        dominant_sign=dominant_sign,
        sign_consistency=round(dominant_count / len(values), 6),
        values=tuple(round(value, 6) for value in values),
    )


def summarize_campaign(
    plan: ExperimentCampaignPlan,
    results: list[CampaignTrialResult] | tuple[CampaignTrialResult, ...],
) -> ExperimentCampaignReport:
    result_by_id = {result.trial_id: result for result in results}
    if len(result_by_id) != len(results):
        raise ValueError("duplicate trial_id in campaign results")

    expected = {trial.trial_id: trial for trial in plan.trials}
    unknown = sorted(set(result_by_id) - set(expected))
    if unknown:
        raise ValueError(f"results contain trials outside campaign plan: {', '.join(unknown)}")

    expected_protocol = _normalized_protocol_template(plan.protocol_template)
    expected_protocol_fingerprint = _canonical_hash(expected_protocol) if expected_protocol else ""

    eligible: list[CampaignTrialResult] = []
    rejected: list[dict[str, str]] = []
    for trial in plan.trials:
        result = result_by_id.get(trial.trial_id)
        if result is None:
            rejected.append({"trial_id": trial.trial_id, "reason": "missing trial result"})
            continue
        if result.seed != trial.seed:
            rejected.append({"trial_id": trial.trial_id, "reason": "trial seed mismatch"})
            continue
        if expected_protocol_fingerprint and result.protocol_fingerprint != expected_protocol_fingerprint:
            rejected.append({"trial_id": trial.trial_id, "reason": "trial protocol fingerprint mismatch"})
            continue
        if result.attribution_eligible and result.attestation_verified and result.protocol_match:
            eligible.append(result)
        else:
            rejected.append({
                "trial_id": trial.trial_id,
                "reason": result.rejection_reason or "causal attribution not eligible, not verified, or protocol mismatched",
            })

    outcome_names = sorted({name for result in eligible for name in result.outcomes})
    behavior_names = sorted({name for result in eligible for name in result.behavioral_outcomes})
    outcome_metrics: dict[str, MetricReplicationSummary] = {}
    behavioral_metrics: dict[str, MetricReplicationSummary] = {}

    for name in outcome_names:
        values = [result.outcomes[name] for result in eligible if name in result.outcomes]
        if values:
            outcome_metrics[name] = _metric_summary(name, values)
    for name in behavior_names:
        values = [result.behavioral_outcomes[name] for result in eligible if name in result.behavioral_outcomes]
        if values:
            behavioral_metrics[name] = _metric_summary(name, values)

    report_payload = {
        "campaign_id": plan.campaign_id,
        "campaign_name": plan.campaign_name,
        "trial_count": plan.trial_count,
        "eligible_trial_ids": [result.trial_id for result in eligible],
        "rejected_trials": rejected,
        "outcome_metrics": {key: value.model_dump(mode="json") for key, value in outcome_metrics.items()},
        "behavioral_metrics": {key: value.model_dump(mode="json") for key, value in behavioral_metrics.items()},
    }
    return ExperimentCampaignReport(
        campaign_id=plan.campaign_id,
        campaign_name=plan.campaign_name,
        trial_count=plan.trial_count,
        eligible_trial_count=len(eligible),
        rejected_trial_count=len(rejected),
        eligible_trial_ids=tuple(result.trial_id for result in eligible),
        rejected_trials=tuple(rejected),
        outcome_metrics=outcome_metrics,
        behavioral_metrics=behavioral_metrics,
        report_fingerprint=_canonical_hash(report_payload),
    )