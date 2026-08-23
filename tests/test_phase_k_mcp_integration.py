from __future__ import annotations

from worldos_core.behavioral_phenotype import BehavioralPhenotypeComparison
from worldos_core.mcp_server import _campaign_behavioral_metrics, build_mcp


def _comparison() -> BehavioralPhenotypeComparison:
    return BehavioralPhenotypeComparison(
        name="scarcity",
        treatment_timeline="treatment",
        control_timeline="control",
        treatment_fingerprint="a" * 64,
        control_fingerprint="b" * 64,
        identical=False,
        event_count_delta=3,
        participant_count_delta=1,
        first_tick_delta=-2,
        last_tick_delta=4,
        active_tick_span_delta=6,
        burst_tick_count_delta=2,
        peak_events_per_tick_delta=1,
        event_type_deltas={"scarcity.purchase": 3},
        participant_event_deltas={"人物-001": 2},
        comparison_fingerprint="c" * 64,
    )


def test_campaign_behavioral_metrics_merge_phenotype_comparison() -> None:
    metrics = _campaign_behavioral_metrics(
        {"custom.behavior": 7.0},
        [_comparison().model_dump(mode="json")],
    )
    assert metrics["custom.behavior"] == 7.0
    assert metrics["phenotype.scarcity.event_count_delta"] == 3.0
    assert metrics["phenotype.scarcity.first_tick_delta"] == -2.0
    assert metrics["phenotype.scarcity.burst_tick_count_delta"] == 2.0


def test_phase_k_read_only_tools_are_registered(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WORLDOS_DB", str(tmp_path / "world.db"))
    monkeypatch.setenv("WORLDOS_MCP_TOKEN", "d" * 64)
    monkeypatch.setenv("WORLDOS_MCP_PUBLIC_URL", "https://worldos.example/mcp")
    monkeypatch.setenv("WORLDOS_MCP_ISSUER_URL", "https://worldos.example/auth")
    server = build_mcp()
    tools = getattr(getattr(server, "_tool_manager", None), "_tools", {})
    if tools:
        names = set(tools)
        assert "behavioral_trajectory" in names
        assert "compare_behavioral_trajectory" in names
        assert "behavioral_phenotype" in names
        assert "compare_behavioral_phenotype" in names
