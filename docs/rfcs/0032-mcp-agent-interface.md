# RFC 0032 — WorldOS MCP Agent Interface

## Status

Proposed.

## Goal

Expose WorldOS as a semantic agent tool surface over Model Context Protocol (MCP), allowing ChatGPT and other MCP-capable agents to inspect, experiment with, and control worlds without understanding WorldOS HTTP routes, cookies, database layout, or event-store internals.

The MCP layer is an adapter, not a second business API. It reuses RFC 0030 Debug API and RFC 0031 Remote Control API semantics, including world hashes, persistent idempotency, event sourcing, branch safety, and command status.

## Architectural position

```text
Agent / ChatGPT / OpenClaw / Hermes / Codex
                    |
                    v
          WorldOS MCP Server
                    |
         semantic tool boundary
                    |
          +---------+---------+
          |                   |
          v                   v
   Debug API (read)     Control API (write)
          |                   |
          +---------+---------+
                    |
              WorldOS Engine
                    |
      Event Store / Projections / Runner
```

The MCP server MUST NOT access SQLite world files directly and MUST NOT mutate projections directly. All reads and writes must go through existing WorldOS application services or the equivalent internal service methods shared with the HTTP APIs.

## Design principles

1. **Semantic tools, not HTTP wrappers.** Tool names describe user intent (`advance_world`, `inspect_actor`) rather than URLs.
2. **Read/write separation.** Read tools are side-effect free. Mutation tools are explicitly marked as write operations.
3. **Fail closed.** Every existing-world mutation requires an expected world hash. Missing or stale hashes are rejected.
4. **Persistent idempotency.** Every mutation uses a stable idempotency key backed by RFC 0031 `control_commands.db`.
5. **Event-sourced mutations only.** No raw SQL, arbitrary filesystem access, or direct projection replacement.
6. **Disposable experiments by default.** Destructive experiments should create a temporary world or branch rather than modifying a user world.
7. **Explainability.** Tool responses include enough identity, version, tick, hash, command, and event metadata to reconstruct why a result occurred.
8. **Client independence.** The semantic service layer must be reusable outside MCP.

## MCP transport

The production/development deployment SHOULD expose a remote HTTPS MCP endpoint, for example:

`https://worldos.255202.xyz/mcp`

The MCP service runs as a separate process/container behind the existing edge proxy. It is not embedded into the Inspector request handler.

Recommended topology:

```text
Cloudflare
    |
   Caddy
    |
    +---- / -----------------> worldos-proxy -> Inspector
    |
    +---- /mcp --------------> worldos-mcp
```

The MCP container and WorldOS services may share internal Python service modules; MCP must not call public WorldOS HTTP endpoints through the internet when it is deployed in the same application stack.

## Authentication and authorization

### Development

Initial development authentication may use a dedicated runtime secret:

`WORLDOS_MCP_TOKEN`

It MUST be distinct from `WORLDOS_DEBUG_TOKEN` and `WORLDOS_CONTROL_TOKEN`.

The secret must not be committed or returned by normal diagnostic tools.

### Future multi-user deployment

The MCP boundary should support OAuth/OIDC and scopes. Proposed scopes:

- `world.read`
- `world.create`
- `world.advance`
- `world.branch`
- `world.stimulus`
- `world.delete`
- `world.restore`
- `world.admin`

The internal service methods MUST enforce scope requirements independently of MCP tool descriptions.

## Tool taxonomy

### Level 1 — Discovery and health

#### `worldos_health`

Purpose: verify connectivity and version before every experiment session.

Input: none.

Output includes:

- runtime version
- VCS ref
- MCP protocol/server version
- read/write capabilities
- maximum ticks per request
- persistent idempotency status

#### `list_worlds`

Purpose: discover available worlds.

Input:

```json
{
  "include_protected": true
}
```

Output per world:

- world_id
- name
- protected/disposable flags
- current tick
- event count
- current world hash
- runtime status

### Level 2 — World inspection

#### `probe_world`

Primary one-call inspection tool.

Input:

```json
{
  "world_id": "world-c607e0a5",
  "timeline_id": "main",
  "recent_event_limit": 30
}
```

Output includes:

- tick / event count / world hash
- locations
- actors and survival state
- active goals/plans
- social bonds and obligations
- recent important events
- diagnostic warnings
- narrator summary/context

#### `inspect_actor`

Input:

```json
{
  "world_id": "...",
  "actor_id": "人物-001",
  "timeline_id": "main"
}
```

Output includes:

- identity and location
- health/needs/inventory
- personality and long-term motives
- current goal and plan
- beliefs and memory summaries
- relationships
- obligations owed / receivable
- recent important actions

#### `query_events`

Structured event search.

Input filters MAY include:

- world_id
- timeline_id
- event_type
- actor_id
- subject_id
- tick range
- correlation_id
- limit

The default output should return compact event summaries plus stable event identifiers. Raw payloads are optional and should require `include_payload=true`.

#### `inspect_social_graph`

Returns relationship edges, trust, affinity, grievance, derived relationship labels, obligations, and optionally clusters derived for inspection purposes.

Derived clusters are observational; this tool must not create factions.

#### `get_narrative_context`

Returns the read-only Narrator context for a world/timeline/window.

### Level 3 — Safe world control

#### `create_world`

Creates a disposable experimental world.

Input:

```json
{
  "config": {
    "name": "粮荒实验镇",
    "world_type": "agrarian_town",
    "era": "agrarian",
    "population": 12,
    "location_count": 6,
    "seed": "experiment-famine-001"
  },
  "idempotency_key": "exp-famine-create-v1",
  "reason": "compare social response to scarcity"
}
```

Output includes the created world descriptor and initial world hash.

#### `advance_world`

Input:

```json
{
  "world_id": "...",
  "timeline_id": "main",
  "ticks": 100,
  "expected_world_hash": "...",
  "idempotency_key": "exp-famine-main-advance-100-v1",
  "reason": "observe autonomous response"
}
```

The tool MUST never select a default world when `world_id` is missing.

Output includes:

- tick before/after
- events before/after
- hash before/after
- elapsed/performance metrics if available
- idempotency replay flag

#### `branch_world`

Creates a timeline branch using normal Event Store branch semantics.

Input includes:

- world_id
- source timeline
- branch id
- optional through_sequence
- expected world hash
- idempotency key
- reason

#### `delete_world`

Deletes only a disposable/unprotected world.

Input includes exact `expected_world_hash` plus idempotency key.

Protected sample worlds remain undeletable.

### Level 4 — Experimental stimuli

Generic event injection remains an engineering escape hatch but SHOULD NOT be the normal MCP surface.

Prefer typed domain tools such as:

#### `inject_resource_shock`

Examples:

- reduce harvest yield
- destroy stock
- discover a new resource

#### `inject_information`

Introduces a fact/message through an explicit source/observation mechanism rather than modifying beliefs directly.

#### `inject_environment_event`

Examples:

- drought
- flood
- disease outbreak
- road closure

#### `inject_social_incident`

Examples that the domain model explicitly supports, such as an externally observed dispute or public announcement.

Typed stimulus tools must compile into valid WorldOS commands/events so the resulting history remains replayable.

Until typed domain commands exist, MCP may expose an admin-only `inject_test_event` tool mapped to RFC 0031 `inject-event`, clearly labeled as an engineering escape hatch.

## Command reconciliation

#### `get_command_status`

Input:

```json
{
  "idempotency_key": "exp-famine-main-advance-100-v1"
}
```

Returns the persistent command-ledger record.

MCP mutation execution rule:

1. Generate or reuse a stable idempotency key for the logical command.
2. Execute the command once.
3. If transport result is ambiguous, query `get_command_status`.
4. If `completed`, use the persisted original response.
5. If `in_progress`, fail closed and report an ambiguous command outcome.
6. Never generate a new idempotency key merely to retry an uncertain mutation.

## Higher-level experiment tools

The first MCP release SHOULD keep orchestration in the agent rather than making a giant server-side `run_experiment` tool. This preserves transparency and lets the agent inspect intermediate state.

Typical agent loop:

```text
worldos_health
  -> list_worlds
  -> create_world / branch_world
  -> probe_world
  -> advance_world
  -> probe_world
  -> query_events / inspect_actor / inspect_social_graph
  -> advance_world or apply typed stimulus
  -> compare results
  -> delete disposable world
```

A future `compare_timelines` read tool is useful because it can deterministically compute differences without mutating either branch.

## Proposed first-release tool set

MCP v0.1 SHOULD expose only the smallest coherent set:

Read:

1. `worldos_health`
2. `list_worlds`
3. `probe_world`
4. `inspect_actor`
5. `query_events`
6. `inspect_social_graph`
7. `get_narrative_context`
8. `get_command_status`

Write:

9. `create_world`
10. `advance_world`
11. `branch_world`
12. `inject_test_event` (development/admin only)
13. `delete_world`

This maps closely to capabilities already implemented in RFC 0030/0031 and avoids inventing unsupported domain semantics.

## Tool response envelope

All tools SHOULD use a common envelope:

```json
{
  "ok": true,
  "runtime": {
    "vcs_ref": "...",
    "version": "..."
  },
  "world": {
    "world_id": "...",
    "timeline_id": "main",
    "tick": 100,
    "world_hash": "..."
  },
  "data": {},
  "warnings": []
}
```

Mutation responses additionally include:

```json
{
  "command": {
    "idempotency_key": "...",
    "state": "completed",
    "replayed": false
  }
}
```

## Error model

MCP errors should translate WorldOS failures into stable machine-readable categories:

- `UNAUTHENTICATED`
- `PERMISSION_DENIED`
- `WORLD_NOT_FOUND`
- `ACTOR_NOT_FOUND`
- `STALE_WORLD_HASH`
- `IDEMPOTENCY_KEY_CONFLICT`
- `COMMAND_OUTCOME_UNKNOWN`
- `WORLD_BUSY`
- `WORLD_PROTECTED`
- `INVALID_COMMAND`
- `INTERNAL_ERROR`

The human-readable message should be concise; structured error data should include current hash or command key when safe.

## Safety classifications

Tool metadata should communicate impact:

- read tools: read-only
- `advance_world`: mutating, reversible only through branching/history semantics
- `create_world`: mutating but isolated
- `branch_world`: mutating metadata/history structure, low destructive risk
- `inject_test_event`: high-impact development tool
- `delete_world`: destructive

The server should not falsely mark mutation tools as read-only to bypass client confirmation behavior.

## Protected-world policy

World descriptors should have an explicit protection policy rather than inferring safety from names.

Suggested flags:

```json
{
  "protected": true,
  "allow_advance": true,
  "allow_stimulus": false,
  "allow_delete": false
}
```

Experiments should default to newly created disposable worlds or branches.

## Versioning

The MCP server exposes:

- `worldos_mcp_version` — semantic tool API version
- `worldos_vcs_ref` — deployed code revision
- supported capabilities

Tool schemas follow additive compatibility by default. Removing/renaming a tool or required field requires a major MCP interface version change.

## Observability and audit

Every MCP write must preserve:

- caller/tool identity if available
- idempotency key
- reason
- target world/timeline
- world hash before/after
- command status
- resulting event identifiers when applicable

The existing persistent command ledger remains the source of truth for command idempotency. MCP may add invocation tracing but must not create a second mutation ledger.

Secrets must never be included in invocation traces.

## Implementation phases

### Phase A — semantic service layer

Extract or formalize internal Python application services used by Debug/Control HTTP handlers so both HTTP and MCP call identical logic.

Acceptance:

- no MCP-specific world mutation logic
- HTTP API behavior unchanged
- shared service unit tests

### Phase B — MCP read server

Implement remote MCP transport and the eight read tools.

Acceptance:

- remote health/tool discovery
- same probe results as Debug API
- zero Event Store writes from read tools
- authentication and version reporting

### Phase C — MCP controlled writes

Add create/advance/branch/delete plus command-status integration.

Acceptance:

- stale hash fails closed
- exact same idempotency key/request replays after process restart
- same key/different request conflicts
- no implicit default-world writes
- protected world cannot be deleted

### Phase D — typed stimuli and experiment ergonomics

Replace generic test-event injection for common experiments with domain commands and add read-only comparison/analysis tools.

Candidate tools:

- `compare_timelines`
- `summarize_period`
- `inject_resource_shock`
- `inject_environment_event`
- `inject_information`

## Testing strategy

MCP tests must include:

1. protocol/tool discovery smoke test
2. auth rejection
3. read/write metadata validation
4. probe parity with Debug API
5. no-write assertion for every read tool
6. create -> advance -> inspect -> branch -> inject -> delete end-to-end
7. stale-hash rejection
8. idempotent replay before and after restart
9. same-key conflict
10. protected-world deletion rejection
11. original-world zero-pollution experiment test
12. 10,000-tick run through `advance_world`

## Deployment

Add a separate `mcp` service to Compose. The process reads the same persistent WorldOS data mount only if required by the shared service architecture; preferred design is shared application-service code with normal datastore abstractions, never direct ad-hoc SQL.

Recommended environment variables:

```text
WORLDOS_MCP_ENABLED=true
WORLDOS_MCP_TOKEN=<runtime secret>
WORLDOS_MCP_BIND=0.0.0.0
WORLDOS_MCP_PORT=8766
```

The Caddy route exposes `/mcp` over HTTPS. Normal Inspector and HTTP API routes remain unchanged.

## ChatGPT integration note

WorldOS MCP is designed as a standards-compatible server rather than around a single ChatGPT plan or client. ChatGPT deployment capability should be treated as a client concern: the WorldOS server remains useful for any MCP-compatible agent even when a particular ChatGPT account cannot enable write-capable custom MCP apps.

## Non-goals

- No raw SQL tool.
- No shell/SSH tool.
- No arbitrary file reader/writer.
- No direct belief/memory/relationship projection editing.
- No hidden plot-director mutation path.
- No tool that silently chooses a target world for writes.
- No bypass of Event Store, world-hash concurrency, or persistent command idempotency.
