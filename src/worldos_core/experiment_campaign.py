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
        if self.attribution_eligible and self.attestation_verified:
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


def trial_result_from_causal_report(
    *,
    trial_id: str,
    seed: str,
    causal_report: dict[str, Any],
    behavioral_outcomes: dict[str, float] | None = None,
) -> CampaignTrialResult:
    attribution = causal_report.get("attribution", {}) if isinstance(causal_report, dict) else {}
    pre = causal_report.get("pre_treatment_equivalence", {}) if isinstance(causal_report, dict) else {}
    selected = causal_report.get("selected_outcomes", {}) if isinstance(causal_report, dict) else {}

    outcomes: dict[str, float] = {}
    for key, value in selected.items() if isinstance(selected, dict) else ():
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            outcomes[str(key)] = float(value)

    eligible = bool(attribution.get("eligible"))
    verified = bool(pre.get("attestation_verified"))
    reason = None
    if not eligible or not verified:
        errors = pre.get("verification_errors") if isinstance(pre, dict) else None
        if isinstance(errors, list) and errors:
            reason = "; ".join(str(item) for item in errors)
        else:
            reason = str(attribution.get("reason") or "trial is not causally eligible")

    fingerprint_payload = {
        "trial_id": trial_id,
        "seed": seed,
        "attestation_digest": str(pre.get("attestation_digest") or ""),
        "attribution_eligible": eligible,
        "attestation_verified": verified,
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
        if result.attribution_eligible and result.attestation_verified:
            eligible.append(result)
        else:
            rejected.append({
                "trial_id": trial.trial_id,
                "reason": result.rejection_reason or "causal attribution not eligible or not verified",
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