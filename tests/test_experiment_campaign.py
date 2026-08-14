import pytest
from pydantic import ValidationError

from worldos_core.experiment_campaign import (
    CampaignTrialResult,
    build_campaign_plan,
    summarize_campaign,
    trial_result_from_causal_report,
)


def _eligible(trial_id: str, seed: str, value: float, behavior: float) -> CampaignTrialResult:
    return CampaignTrialResult(
        trial_id=trial_id,
        seed=seed,
        attestation_digest=f"att-{trial_id}",
        attribution_eligible=True,
        attestation_verified=True,
        outcomes={"inventory_delta": value},
        behavioral_outcomes={"conflict_count_delta": behavior},
        source_fingerprint=f"src-{trial_id}",
    )


def test_campaign_plan_is_deterministic():
    kwargs = dict(
        campaign_name="scarcity memory replication",
        base_seed="phase-j-001",
        trial_count=5,
        protocol_template={"treatment": "retain", "control": "suppress"},
    )
    first = build_campaign_plan(**kwargs)
    second = build_campaign_plan(**kwargs)
    assert first == second
    assert first.campaign_id.startswith("campaign-")
    assert len(first.trials) == 5
    assert len({trial.seed for trial in first.trials}) == 5
    assert [trial.ordinal for trial in first.trials] == [1, 2, 3, 4, 5]


def test_changed_protocol_changes_campaign_identity():
    first = build_campaign_plan(campaign_name="x", base_seed="seed", trial_count=5, protocol_template={"treatment": "retain"})
    second = build_campaign_plan(campaign_name="x", base_seed="seed", trial_count=5, protocol_template={"treatment": "suppress"})
    assert first.campaign_id != second.campaign_id
    assert [trial.seed for trial in first.trials] != [trial.seed for trial in second.trials]


def test_campaign_summary_aggregates_only_verified_eligible_trials():
    plan = build_campaign_plan(campaign_name="replication", base_seed="seed", trial_count=5)
    results = [
        _eligible(plan.trials[0].trial_id, plan.trials[0].seed, -3.0, -1.0),
        _eligible(plan.trials[1].trial_id, plan.trials[1].seed, -5.0, -2.0),
        _eligible(plan.trials[2].trial_id, plan.trials[2].seed, -4.0, -1.0),
        CampaignTrialResult(
            trial_id=plan.trials[3].trial_id,
            seed=plan.trials[3].seed,
            attribution_eligible=False,
            attestation_verified=False,
            outcomes={"inventory_delta": 999.0},
            rejection_reason="tampered attestation",
        ),
    ]
    report = summarize_campaign(plan, results)
    assert report.eligible_trial_count == 3
    assert report.rejected_trial_count == 2
    assert report.outcome_metrics["inventory_delta"].mean == -4.0
    assert report.outcome_metrics["inventory_delta"].median == -4.0
    assert report.outcome_metrics["inventory_delta"].negative_count == 3
    assert report.outcome_metrics["inventory_delta"].sign_consistency == 1.0
    assert report.behavioral_metrics["conflict_count_delta"].mean == pytest.approx(-4 / 3, abs=1e-6)
    assert {item["reason"] for item in report.rejected_trials} == {"tampered attestation", "missing trial result"}


def test_campaign_summary_is_deterministic_independent_of_result_input_order():
    plan = build_campaign_plan(campaign_name="replication", base_seed="seed", trial_count=3)
    results = [
        _eligible(plan.trials[0].trial_id, plan.trials[0].seed, 1.0, 2.0),
        _eligible(plan.trials[1].trial_id, plan.trials[1].seed, 2.0, 3.0),
        _eligible(plan.trials[2].trial_id, plan.trials[2].seed, 3.0, 4.0),
    ]
    first = summarize_campaign(plan, results)
    second = summarize_campaign(plan, list(reversed(results)))
    assert first == second
    assert first.report_fingerprint == second.report_fingerprint
    assert first.outcome_metrics["inventory_delta"].values == (1.0, 2.0, 3.0)


def test_seed_mismatch_is_rejected_not_silently_aggregated():
    plan = build_campaign_plan(campaign_name="replication", base_seed="seed", trial_count=2)
    report = summarize_campaign(
        plan,
        [
            _eligible(plan.trials[0].trial_id, "wrong-seed", 10.0, 1.0),
            _eligible(plan.trials[1].trial_id, plan.trials[1].seed, 2.0, 1.0),
        ],
    )
    assert report.eligible_trial_count == 1
    assert report.rejected_trial_count == 1
    assert report.rejected_trials[0]["reason"] == "trial seed mismatch"
    assert report.outcome_metrics["inventory_delta"].values == (2.0,)


def test_trial_result_from_causal_report_requires_verified_attribution():
    causal = {
        "pre_treatment_equivalence": {
            "attestation_verified": True,
            "attestation_digest": "abc",
        },
        "attribution": {"eligible": True, "reason": "verified"},
        "selected_outcomes": {"average_hunger": -2.5, "nested": {"ignored": 1}},
    }
    result = trial_result_from_causal_report(
        trial_id="trial-1",
        seed="seed-1",
        causal_report=causal,
        behavioral_outcomes={"conflict_count_delta": -3},
    )
    assert result.attribution_eligible is True
    assert result.attestation_verified is True
    assert result.attestation_digest == "abc"
    assert result.outcomes == {"average_hunger": -2.5}
    assert result.behavioral_outcomes == {"conflict_count_delta": -3.0}
    assert result.source_fingerprint


def test_eligible_trial_cannot_exist_without_auditable_evidence():
    with pytest.raises(ValidationError, match="attestation_digest"):
        CampaignTrialResult(
            trial_id="trial-1",
            seed="seed-1",
            attribution_eligible=True,
            attestation_verified=True,
            source_fingerprint="source",
        )
    with pytest.raises(ValidationError, match="source_fingerprint"):
        CampaignTrialResult(
            trial_id="trial-1",
            seed="seed-1",
            attestation_digest="att",
            attribution_eligible=True,
            attestation_verified=True,
        )


def test_tied_effect_sign_is_reported_as_mixed_not_arbitrarily_positive_or_zero():
    plan = build_campaign_plan(campaign_name="tie", base_seed="seed", trial_count=2)
    report = summarize_campaign(
        plan,
        [
            _eligible(plan.trials[0].trial_id, plan.trials[0].seed, -1.0, 1.0),
            _eligible(plan.trials[1].trial_id, plan.trials[1].seed, 1.0, -1.0),
        ],
    )
    summary = report.outcome_metrics["inventory_delta"]
    assert summary.dominant_sign == "mixed"
    assert summary.sign_consistency == 0.5


def test_campaign_rejects_unknown_and_duplicate_trial_ids():
    plan = build_campaign_plan(campaign_name="replication", base_seed="seed", trial_count=2)
    with pytest.raises(ValueError, match="outside campaign plan"):
        summarize_campaign(plan, [_eligible("unknown", "seed", 1, 1)])

    duplicate = _eligible(plan.trials[0].trial_id, plan.trials[0].seed, 1, 1)
    with pytest.raises(ValueError, match="duplicate trial_id"):
        summarize_campaign(plan, [duplicate, duplicate])