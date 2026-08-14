from __future__ import annotations

import hmac
import os
from pathlib import Path
from typing import Any

import httpx
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from pydantic import AnyHttpUrl

from .agent_services import WorldReadService
from .effective_memory import effective_memory_view
from .experiment_protocol import (
    ExperimentArm,
    ExperimentProtocol,
    PreTreatmentAttestation,
    attest_pre_treatment,
    causal_report,
    validate_pre_treatment,
    verify_pre_treatment_attestation,
)
from .experimental_state import ExperimentalCheckpoint, build_atomic_physical_override_event, capture_experimental_checkpoint
from .experiments import compare_probes
from .inspector import WorldInspector
from .memory_interventions import MemoryIntervention, build_memory_intervention_event
from .semantic_stimulus import SemanticStimulus, semantic_event
from .sqlite_store import SQLiteEventStore

READ_SCOPE = "world:read"
WRITE_SCOPE = "world:write"


class StaticMCPTokenVerifier(TokenVerifier):
    async def verify_token(self, token: str) -> AccessToken | None:
        configured = os.environ.get("WORLDOS_MCP_TOKEN", "").strip()
        if not configured or len(configured) < 32 or not hmac.compare_digest(configured, token):
            return None
        return AccessToken(token=token, client_id="worldos-agent", scopes=[READ_SCOPE, WRITE_SCOPE])


def _database_path() -> Path:
    return Path(os.environ.get("WORLDOS_DB", "/data/world.db"))


def _service() -> WorldReadService:
    return WorldReadService(_database_path())


def _bundle(world_id: str, timeline: str):
    service = _service()
    descriptor = service.catalog.get(world_id)
    with SQLiteEventStore(descriptor.database_path) as store:
        return WorldInspector(store).bundle(timeline)


def _control_base_url() -> str:
    return os.environ.get("WORLDOS_CONTROL_INTERNAL_URL", "http://inspector:8765/api/control").rstrip("/")


def _control_token() -> str:
    token = os.environ.get("WORLDOS_CONTROL_TOKEN", "").strip()
    if len(token) < 32:
        raise RuntimeError("WORLDOS_CONTROL_TOKEN is not configured for MCP write tools")
    return token


def _control_request(method: str, path: str, *, payload: dict[str, Any] | None = None, idempotency_key: str | None = None, if_match: str | None = None) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {_control_token()}"}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    if if_match:
        headers["If-Match"] = if_match
    with httpx.Client(timeout=120.0) as client:
        response = client.request(method, _control_base_url() + path, json=payload, headers=headers)
    try:
        body = response.json()
    except ValueError:
        body = {"error": response.text}
    if response.status_code >= 400:
        raise RuntimeError(f"WorldOS Control API {response.status_code}: {body.get('error', body)}")
    if isinstance(body, dict):
        body["http_status"] = response.status_code
        body["idempotency_replayed"] = response.headers.get("Idempotency-Replayed", "").lower() == "true"
    return body


def _inject_experimental_event(world_id: str, timeline_id: str, expected_world_hash: str, idempotency_key: str, reason: str, event: Any) -> dict[str, Any]:
    return _control_request(
        "POST",
        f"/worlds/{world_id}/inject-event",
        payload={
            "event": event.model_dump(mode="json") if hasattr(event, "model_dump") else event,
            "timeline_id": timeline_id,
            "expected_world_hash": expected_world_hash,
            "idempotency_key": idempotency_key,
            "reason": reason,
        },
        idempotency_key=idempotency_key,
    )


def _apply_physical_checkpoint_request(
    world_id: str,
    checkpoint: dict[str, Any],
    expected_world_hash: str,
    idempotency_key: str,
    reason: str,
    *,
    timeline_id: str = "main",
) -> dict[str, Any]:
    """Compile and send a physical override without pre-empting Control replay semantics."""
    bundle = _bundle(world_id, timeline_id)
    manifest = ExperimentalCheckpoint.model_validate(checkpoint)
    event = build_atomic_physical_override_event(bundle.world, manifest, tick=bundle.world.tick)
    return _inject_experimental_event(world_id, timeline_id, expected_world_hash, idempotency_key, reason, event)


def _apply_memory_intervention_request(
    world_id: str,
    intervention: dict[str, Any],
    expected_world_hash: str,
    idempotency_key: str,
    reason: str,
    *,
    timeline_id: str = "main",
    actor_id: str | None = None,
) -> dict[str, Any]:
    """Compile and send a memory intervention without local stale-hash rejection."""
    bundle = _bundle(world_id, timeline_id)
    event = build_memory_intervention_event(
        MemoryIntervention.model_validate(intervention),
        tick=bundle.world.tick,
        actor_id=actor_id,
    )
    return _inject_experimental_event(world_id, timeline_id, expected_world_hash, idempotency_key, reason, event)


def _apply_semantic_stimulus_request(
    world_id: str,
    stimulus: dict[str, Any],
    expected_world_hash: str,
    idempotency_key: str,
    reason: str,
    *,
    timeline_id: str = "main",
    experiment_id: str | None = None,
) -> dict[str, Any]:
    probe = _service().probe_world(world_id, timeline=timeline_id, limit=1)
    tick = int(probe["snapshot"]["current_tick"])
    event = semantic_event(tick=tick, stimulus=SemanticStimulus.model_validate(stimulus), experiment_id=experiment_id)
    return _inject_experimental_event(world_id, timeline_id, expected_world_hash, idempotency_key, reason, event)


def _protocol(
    checkpoint_digest: str,
    treatment_timeline: str,
    control_timeline: str,
    treatment_intervention: dict[str, Any],
    control_intervention: dict[str, Any],
    actor_ids: list[str] | None = None,
) -> ExperimentProtocol:
    return ExperimentProtocol(
        checkpoint_digest=checkpoint_digest,
        treatment=ExperimentArm(name="treatment", timeline_id=treatment_timeline, declared_intervention=treatment_intervention),
        control=ExperimentArm(name="control", timeline_id=control_timeline, declared_intervention=control_intervention),
        actor_ids=tuple(actor_ids or ()),
    )


def build_mcp() -> FastMCP:
    public_url = os.environ.get("WORLDOS_MCP_PUBLIC_URL", "https://worldos.invalid/mcp").strip()
    issuer_url = os.environ.get("WORLDOS_MCP_ISSUER_URL", "https://worldos.invalid/auth").strip()
    mcp = FastMCP(
        "WorldOS",
        instructions="Observe first, mutate explicit worlds only, preserve hashes and idempotency keys, and use experiment checkpoints for causal comparisons.",
        stateless_http=True,
        json_response=True,
        host=os.environ.get("WORLDOS_MCP_HOST", "0.0.0.0"),
        port=int(os.environ.get("WORLDOS_MCP_PORT", "8766")),
        token_verifier=StaticMCPTokenVerifier(),
        auth=AuthSettings(issuer_url=AnyHttpUrl(issuer_url), resource_server_url=AnyHttpUrl(public_url), required_scopes=[READ_SCOPE]),
    )

    @mcp.tool()
    def worldos_health() -> dict[str, Any]:
        return _service().health()

    @mcp.tool()
    def list_worlds() -> dict[str, Any]:
        return _service().list_worlds()

    @mcp.tool()
    def probe_world(world_id: str, timeline: str = "main", limit: int = 50) -> dict[str, Any]:
        return _service().probe_world(world_id, timeline=timeline, limit=limit)

    @mcp.tool()
    def get_timeline_lineage(world_id: str, timeline: str = "main") -> dict[str, Any]:
        return _service().get_timeline_lineage(world_id, timeline=timeline)

    @mcp.tool()
    def inspect_actor(world_id: str, actor_id: str, timeline: str = "main") -> dict[str, Any]:
        return _service().inspect_actor(world_id, actor_id, timeline=timeline)

    @mcp.tool()
    def inspect_effective_memory(world_id: str, actor_id: str, timeline: str = "main") -> dict[str, Any]:
        """Inspect branch-local effective memory immediately, without requiring another tick."""
        bundle = _bundle(world_id, timeline)
        return effective_memory_view(bundle.events, actor_id=actor_id, current_tick=bundle.world.tick)

    @mcp.tool()
    def query_events(world_id: str, timeline: str = "main", event_type: str | None = None, actor_id: str | None = None, subject_id: str | None = None, tick: int | None = None, correlation_id: str | None = None, limit: int = 100) -> dict[str, Any]:
        return _service().query_events(world_id, timeline=timeline, event_type=event_type, actor_id=actor_id, subject_id=subject_id, tick=tick, correlation_id=correlation_id, limit=limit)

    @mcp.tool()
    def inspect_social_graph(world_id: str, timeline: str = "main") -> dict[str, Any]:
        return _service().inspect_social_graph(world_id, timeline=timeline)

    @mcp.tool()
    def get_narrative_context(world_id: str, timeline: str = "main", actor_id: str | None = None, from_sequence: int = 1) -> dict[str, Any]:
        return _service().get_narrative_context(world_id, timeline=timeline, actor_id=actor_id, from_sequence=from_sequence)

    @mcp.tool()
    def diagnose_world(world_id: str, timeline: str = "main") -> dict[str, Any]:
        return _service().get_diagnostics(world_id, timeline=timeline)

    @mcp.tool()
    def capture_experiment_checkpoint(world_id: str, timeline_id: str = "main", actor_ids: list[str] | None = None, component_names: list[str] | None = None) -> dict[str, Any]:
        bundle = _bundle(world_id, timeline_id)
        checkpoint = capture_experimental_checkpoint(
            bundle.world,
            timeline_id=timeline_id,
            source_sequence=len(bundle.events),
            actor_ids=actor_ids,
            component_names=component_names or None,
        ) if component_names is not None else capture_experimental_checkpoint(
            bundle.world,
            timeline_id=timeline_id,
            source_sequence=len(bundle.events),
            actor_ids=actor_ids,
        )
        return checkpoint.model_dump(mode="json")

    @mcp.tool()
    def validate_experiment_equivalence(world_id: str, treatment_timeline: str, control_timeline: str, checkpoint_digest: str, treatment_intervention: dict[str, Any], control_intervention: dict[str, Any], actor_ids: list[str] | None = None) -> dict[str, Any]:
        protocol = _protocol(checkpoint_digest, treatment_timeline, control_timeline, treatment_intervention, control_intervention, actor_ids)
        return validate_pre_treatment(protocol, _bundle(world_id, treatment_timeline).world, _bundle(world_id, control_timeline).world)

    @mcp.tool()
    def attest_experiment_equivalence(world_id: str, treatment_timeline: str, control_timeline: str, checkpoint_digest: str, treatment_intervention: dict[str, Any], control_intervention: dict[str, Any], actor_ids: list[str] | None = None) -> dict[str, Any]:
        """Create a deterministic historical anchor for later post-outcome causal reporting."""
        protocol = _protocol(checkpoint_digest, treatment_timeline, control_timeline, treatment_intervention, control_intervention, actor_ids)
        treatment_bundle = _bundle(world_id, treatment_timeline)
        control_bundle = _bundle(world_id, control_timeline)
        return attest_pre_treatment(
            protocol,
            treatment_bundle.world,
            control_bundle.world,
            treatment_event_count=len(treatment_bundle.events),
            control_event_count=len(control_bundle.events),
        ).model_dump(mode="json")

    @mcp.tool()
    def create_world(config: dict[str, Any], idempotency_key: str, reason: str) -> dict[str, Any]:
        return _control_request("POST", "/worlds", payload={"config": config, "idempotency_key": idempotency_key, "reason": reason}, idempotency_key=idempotency_key)

    @mcp.tool()
    def advance_world(world_id: str, ticks: int, expected_world_hash: str, idempotency_key: str, reason: str, timeline_id: str = "main") -> dict[str, Any]:
        return _control_request("POST", f"/worlds/{world_id}/advance", payload={"ticks": ticks, "timeline_id": timeline_id, "expected_world_hash": expected_world_hash, "idempotency_key": idempotency_key, "reason": reason}, idempotency_key=idempotency_key)

    @mcp.tool()
    def branch_world(world_id: str, branch_id: str, expected_world_hash: str, idempotency_key: str, reason: str, timeline_id: str = "main", through_sequence: int | None = None) -> dict[str, Any]:
        payload = {"branch_id": branch_id, "timeline_id": timeline_id, "expected_world_hash": expected_world_hash, "idempotency_key": idempotency_key, "reason": reason}
        if through_sequence is not None:
            payload["through_sequence"] = through_sequence
        return _control_request("POST", f"/worlds/{world_id}/branch", payload=payload, idempotency_key=idempotency_key)

    @mcp.tool()
    def inject_world_event(world_id: str, event: dict[str, Any], expected_world_hash: str, idempotency_key: str, reason: str, timeline_id: str = "main") -> dict[str, Any]:
        return _inject_experimental_event(world_id, timeline_id, expected_world_hash, idempotency_key, reason, event)

    @mcp.tool()
    def apply_physical_checkpoint(world_id: str, checkpoint: dict[str, Any], expected_world_hash: str, idempotency_key: str, reason: str, timeline_id: str = "main") -> dict[str, Any]:
        return _apply_physical_checkpoint_request(world_id, checkpoint, expected_world_hash, idempotency_key, reason, timeline_id=timeline_id)

    @mcp.tool()
    def apply_memory_intervention(world_id: str, intervention: dict[str, Any], expected_world_hash: str, idempotency_key: str, reason: str, timeline_id: str = "main", actor_id: str | None = None) -> dict[str, Any]:
        return _apply_memory_intervention_request(world_id, intervention, expected_world_hash, idempotency_key, reason, timeline_id=timeline_id, actor_id=actor_id)

    @mcp.tool()
    def apply_semantic_stimulus(world_id: str, stimulus: dict[str, Any], expected_world_hash: str, idempotency_key: str, reason: str, timeline_id: str = "main", experiment_id: str | None = None) -> dict[str, Any]:
        return _apply_semantic_stimulus_request(world_id, stimulus, expected_world_hash, idempotency_key, reason, timeline_id=timeline_id, experiment_id=experiment_id)

    @mcp.tool()
    def compare_timelines(world_id: str, control_timeline: str, experiment_timeline: str, limit: int = 50) -> dict[str, Any]:
        return compare_probes(_service().probe_world(world_id, timeline=control_timeline, limit=limit), _service().probe_world(world_id, timeline=experiment_timeline, limit=limit))

    @mcp.tool()
    def causal_experiment_report(world_id: str, treatment_timeline: str, control_timeline: str, checkpoint_digest: str, treatment_intervention: dict[str, Any], control_intervention: dict[str, Any], outcome_names: list[str] | None = None, actor_ids: list[str] | None = None, limit: int = 50, pre_treatment_attestation: dict[str, Any] | None = None) -> dict[str, Any]:
        protocol = _protocol(checkpoint_digest, treatment_timeline, control_timeline, treatment_intervention, control_intervention, actor_ids)
        treatment_bundle = _bundle(world_id, treatment_timeline)
        control_bundle = _bundle(world_id, control_timeline)
        if pre_treatment_attestation is not None:
            pre = verify_pre_treatment_attestation(
                protocol,
                PreTreatmentAttestation.model_validate(pre_treatment_attestation),
                treatment_history=treatment_bundle.events,
                control_history=control_bundle.events,
            )
        else:
            pre = validate_pre_treatment(protocol, treatment_bundle.world, control_bundle.world)
        return causal_report(
            protocol,
            pre_treatment=pre,
            treatment_probe=_service().probe_world(world_id, timeline=treatment_timeline, limit=limit),
            control_probe=_service().probe_world(world_id, timeline=control_timeline, limit=limit),
            outcome_names=tuple(outcome_names or ()),
        )

    @mcp.tool()
    def delete_world(world_id: str, expected_world_hash: str, idempotency_key: str, reason: str) -> dict[str, Any]:
        if not reason.strip():
            raise ValueError("reason is required")
        return _control_request("DELETE", f"/worlds/{world_id}", idempotency_key=idempotency_key, if_match=expected_world_hash)

    @mcp.tool()
    def control_command_status(idempotency_key: str) -> dict[str, Any]:
        return _control_request("GET", f"/commands/{idempotency_key}")

    return mcp


def main() -> None:
    build_mcp().run(transport="streamable-http")


if __name__ == "__main__":
    main()
