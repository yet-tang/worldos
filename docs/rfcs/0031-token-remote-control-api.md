# RFC 0031 — Token Remote Control API

## Status

Implemented for development environments.

## Goal

Allow an external engineering agent to create controlled test worlds, advance them, branch history, inject event-sourced stimuli, delete disposable worlds, and immediately inspect the result through RFC 0030 Debug API without SSH access.

## Security boundary

- Read API: `WORLDOS_DEBUG_TOKEN` under `/api/debug/*`.
- Write API: `WORLDOS_CONTROL_TOKEN` under `/api/control/*`.
- Both tokens must be supplied at runtime and must never be committed.
- Control token must contain at least 32 characters.
- Nginx disables access logs for both token API prefixes.
- Query-string token authentication exists for tool compatibility; Bearer authentication is preferred.
- The control API is disabled when `WORLDOS_CONTROL_TOKEN` is unset.

## Mutation rules

World mutations must go through WorldOS abstractions and the event store. The API must not expose SQL, arbitrary filesystem access, or direct projection replacement.

Existing-world mutations require optimistic concurrency:

- JSON mutations require `expected_world_hash`.
- DELETE requires `If-Match: <world_hash>`.
- Hash mismatch returns HTTP 409 without applying the command.

Mutating requests also carry an `idempotency_key` and a human-readable `reason`. The key is currently recorded in command responses as the request identity; persistent replay suppression is a follow-up requirement before this API is used across unreliable automatic retry loops. Clients MUST NOT automatically retry a mutation after an ambiguous network failure until persistent idempotency is implemented.

## Endpoints

### Health / capabilities

`GET /api/control/health`

### Create disposable world

`POST /api/control/worlds`

Body is a `WorldConfig`, optionally wrapped as `{ "config": {...} }`.

### Advance a world

`POST /api/control/worlds/{world_id}/advance`

```json
{
  "timeline_id": "main",
  "ticks": 20,
  "expected_world_hash": "...",
  "idempotency_key": "experiment-123-step-1",
  "reason": "observe autonomous social behavior"
}
```

Maximum: 10,000 ticks per request.

### Branch timeline

`POST /api/control/worlds/{world_id}/branch`

```json
{
  "timeline_id": "main",
  "branch_id": "experiment-b",
  "through_sequence": 1234,
  "expected_world_hash": "...",
  "idempotency_key": "experiment-123-branch",
  "reason": "compare alternative intervention"
}
```

### Inject event-sourced stimulus

`POST /api/control/worlds/{world_id}/inject-event`

The `event` object must validate as `NewEvent`. Tick boundary events are rejected. This is an engineering/testing escape hatch: callers should prefer domain commands when a domain command exists.

### Delete disposable world

`DELETE /api/control/worlds/{world_id}` with `If-Match: <world_hash>`.

The protected `first-living-world` cannot be deleted through the catalog.

## Agent validation loop

1. `GET /api/debug/health` and verify deployed VCS SHA.
2. `GET /api/debug/worlds/{id}/probe` and capture hash.
3. Apply one explicit control command using that hash.
4. Probe again and inspect diagnostics/events/actors/social state.
5. Branch or create a disposable world for destructive experiments.
6. Delete disposable worlds after verification.

## Non-goals / follow-ups

- No raw SQL endpoint.
- No direct projection mutation.
- No arbitrary file access.
- Persistent idempotency ledger is required before automatic mutation retries.
- Domain-specific stimulus/command endpoints should gradually replace generic `inject-event` for common experiments.
- Snapshot restore should be added as an explicit event-store operation rather than by replacing database files over HTTP.
