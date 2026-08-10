# RFC 0030 · Token Debug Read API

Status: Implemented in development branch

## Goal

Provide a development-only, machine-readable API that lets maintainers and automated validation tools inspect a running WorldOS instance without relying on browser cookies or the human-facing Inspector UI.

The API is designed for remote verification of a deployed development world: identify the exact runtime revision, inspect world state, drill into actors and social state, query committed events, explain event causality, and detect common replay/runtime inconsistencies.

## Non-goals

- It is not an administration API.
- It does not create, delete, branch, pause, resume, or advance worlds.
- It does not bypass the Event Store or mutate projections.
- It is not enabled unless a token is explicitly configured.
- It does not replace the normal Web Inspector or existing world-control API.

## Authentication

Set `WORLDOS_DEBUG_TOKEN` in the development deployment. A configured token must be at least 24 characters.

Preferred authentication:

```http
Authorization: Bearer <token>
```

Alternative header:

```http
X-WorldOS-Debug-Token: <token>
```

For read-only tooling that cannot attach custom HTTP headers, GET requests may use:

```text
?token=<url-encoded-token>
```

Use a URL-safe random token, for example a 32-byte hex value. The token must never be committed to Git.

The Nginx `/api/debug` locations disable Basic Auth because the application-level token is the authentication boundary. Nginx access logging is disabled for these locations so query-string tokens are not written to that proxy's access log. Upstream/CDN/browser tooling can still retain full URLs, so header authentication remains preferred whenever possible.

If `WORLDOS_DEBUG_TOKEN` is unset, the API returns 404. If it is configured with fewer than 24 characters, the API returns 503 rather than accepting weak authentication.

Token comparison uses constant-time comparison.

## Read-only invariant

Every `/api/debug/*` capability is a read over an existing SQLite Event Store and replayed projections.

The API does not expose a debug mutation endpoint. Advancing the world continues to use the existing explicit world-control path, which has its own world ID checks and per-world writer lock.

A validation request must not change event count, timeline state, world hash, actor state, or catalog contents.

## Runtime identity

Container builds expose:

- `WORLDOS_VCS_REF`
- `WORLDOS_VERSION`

Debug responses include these values so a remote verifier can prove which source revision it is observing rather than assuming that the deployment pulled the intended image.

## Endpoints

All routes are GET-only debug reads.

### `GET /api/debug/health`

Returns API availability, read-only declaration, runtime revision/version, world count, and supported capabilities.

### `GET /api/debug/worlds`

Returns all catalog worlds without filesystem paths. Each readable world includes current completed tick, event count, and canonical world hash.

### `GET /api/debug/worlds/{world_id}/probe`

Primary one-call validation endpoint.

Query parameters:

- `timeline` defaults to `main`
- `limit` controls recent events, default 50, maximum 1000

Returns:

- runtime revision/version
- public world descriptor
- timeline sequence/event count/current completed tick/world hash/flags
- actor and location counts
- actor state summaries
- personality/drives and active goals
- directed social bonds
- open obligations as debtor/creditor
- world-wide social obligation summary
- diagnostics
- recent committed events

### `GET /api/debug/worlds/{world_id}/overview`

Returns the existing replay-backed Web Inspector overview for the specified world/timeline.

### `GET /api/debug/worlds/{world_id}/events`

Filters committed Event Store history.

Supported query parameters:

- `timeline`
- `limit` (1..1000)
- `event_type`
- `actor_id`
- `subject_id`
- `tick`
- `correlation_id`

### `GET /api/debug/worlds/{world_id}/actor/{actor_id}`

Returns the full Inspector actor debug view, including entity state, observations, beliefs, memories, goals, plan steps, social bonds, and open obligations.

### `GET /api/debug/worlds/{world_id}/social`

Returns the replayed `SocialProjection`.

### `GET /api/debug/worlds/{world_id}/narrative`

Returns read-only Narrator context.

Query parameters:

- `timeline`
- `actor` for actor perspective; omitted means omniscient
- `from_sequence` defaults to 1

### `GET /api/debug/worlds/{world_id}/diagnostics`

Runs deterministic structural checks over the replayed timeline and reports:

- contiguous event sequence
- tick.started without matching tick.completed
- duplicate tick.completed events
- relationship references to unknown entities
- open social obligations already past due
- active goals with no pending work
- recent rejected intents
- event-type counts
- phase counts

Warnings are diagnostics, not automatic mutation or repair.

### `GET /api/debug/worlds/{world_id}/explain-event/{event_id}`

Returns one event plus its direct `caused_by` causes and direct consequences, using the Inspector causal index.

## Recommended development deployment

Generate a token locally or on the VPS:

```bash
openssl rand -hex 32
```

Store it only in the deployment `.env`:

```dotenv
WORLDOS_DEBUG_TOKEN=<generated-value>
```

Then recreate the Inspector container so Compose injects the variable.

Do not print the token in deployment reports. Report only whether the Debug API is enabled and whether authenticated health/probe checks succeeded.

## Validation contract

CI must prove:

1. no configured token => Debug API unavailable;
2. missing/incorrect token => 401;
3. weak configured token => 503;
4. Bearer and query-token authentication both work;
5. world list does not expose database paths;
6. probe returns runtime identity, state, social data, diagnostics, and bounded recent events;
7. event filters and event explanation work;
8. actor/social/narrative reads work;
9. event count remains unchanged after a suite of Debug API requests;
10. Nginx disables access logging and Basic Auth only for `/api/debug` routes;
11. Compose injects `WORLDOS_DEBUG_TOKEN` only from deployment environment.
