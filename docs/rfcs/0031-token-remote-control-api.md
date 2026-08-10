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

Every mutation also requires a stable idempotency key. POST commands accept `idempotency_key` in the JSON body or `Idempotency-Key` as a header. DELETE requires `Idempotency-Key` because it has no JSON body.

### Persistent command ledger

Remote mutations are guarded by a persistent SQLite command ledger at `control_commands.db` in the WorldOS data directory. The ledger is deliberately separate from individual world databases so create/delete responses remain replayable even after a world database is removed.

For each command the ledger stores:

- idempotency key
- canonical request fingerprint
- HTTP method and path
- state (`in_progress` or `completed`)
- original status code and JSON response
- creation/completion timestamps

Semantics:

1. The idempotency key is durably reserved before a mutation starts.
2. Same key + same request + completed command returns the original response without executing the mutation again. The response includes `Idempotency-Replayed: true`.
3. Same key + different request returns HTTP 409.
4. If a process fails after reservation and the outcome cannot be proven, the key remains `in_progress`; retry returns HTTP 409 instead of risking duplicate mutation.
5. Validation/precondition failures known to happen before a write release the reservation, allowing a corrected request to be issued.
6. Ledger records survive service restarts and world deletion.

Clients may inspect a command before retrying:

`GET /api/control/commands/{idempotency_key}`

Automatic retries are allowed only when the exact same command uses the exact same idempotency key. An `in_progress` command must be treated as an ambiguous outcome requiring inspection rather than blind replay.

## Endpoints

### Health / capabilities

`GET /api/control/health`

The health response advertises `persistent_idempotency: true` and the `command-status` capability when the persistent ledger is active.

### Command status

`GET /api/control/commands/{idempotency_key}`

Returns the persisted command state and, for a completed command, the original response.

### Create disposable world

`POST /api/control/worlds`

Body is a `WorldConfig`, optionally wrapped as `{ "config": {...} }`, plus an `idempotency_key` (or the equivalent header).

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

`DELETE /api/control/worlds/{world_id}` with both:

- `If-Match: <world_hash>`
- `Idempotency-Key: <stable-command-key>`

The protected `first-living-world` cannot be deleted through the catalog.

## Agent validation loop

1. `GET /api/debug/health` and verify deployed VCS SHA.
2. `GET /api/debug/worlds/{id}/probe` and capture hash.
3. Apply one explicit control command using that hash and a unique stable idempotency key.
4. If the HTTP result is ambiguous, query `GET /api/control/commands/{key}` before any retry.
5. Probe again and inspect diagnostics/events/actors/social state.
6. Branch or create a disposable world for destructive experiments.
7. Delete disposable worlds after verification using `If-Match` plus an idempotency key.

## Non-goals / follow-ups

- No raw SQL endpoint.
- No direct projection mutation.
- No arbitrary file access.
- Domain-specific stimulus/command endpoints should gradually replace generic `inject-event` for common experiments.
- Snapshot restore should be added as an explicit event-store operation rather than by replacing database files over HTTP.
- A future operator workflow may add explicit reconciliation for commands left `in_progress` after a process crash; such commands are intentionally never auto-replayed.
