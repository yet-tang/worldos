# WorldOS Agent Collaboration Contract

This file defines the repository-level collaboration contract for human operators, architecture/source coordination agents, local development agents, VPS execution agents, and future specialist agents.

## Roles

### Human Owner

The human owner is the final authority for irreversible production decisions, credential rotation, major infrastructure changes, security-policy reductions, destructive migration, and scope changes with material risk.

Routine development, CI, deployment, smoke testing, and acceptance testing should not require the human owner to manually relay instructions between agents.

### Architect Agent

The Architect Agent owns:

- phase goals, non-goals, architecture and public contracts;
- task decomposition and acceptance criteria;
- GitHub Task Contracts for implementation and production acceptance;
- pull-request review and architecture conformance;
- CI diagnosis and source-level remediation direction;
- analysis of VPS execution reports;
- deciding whether work is merge/deploy ready.

The Architect Agent should normally delegate repository implementation to the Local Development Agent instead of requiring the Human Owner to relay code instructions.

### Local Development Agent

The Local Development Agent is the repository implementation engineer. It owns:

- isolated branch/worktree implementation;
- unit and integration tests;
- local runtime validation;
- commits and pull-request updates;
- responding to Architect review and CI failures.

It follows `docs/operations/local-development-agent-protocol.md`.

It must not silently redesign architecture, weaken tests to obtain green CI, access production secrets, deploy production, or mutate production worlds.

Preferred routing labels are `agent:local-dev` + `status:ready`.

### VPS Execution Agent

The VPS execution agent is the production executor. It owns:

- deployment of explicitly specified versions;
- production smoke tests;
- E2E acceptance execution;
- evidence collection;
- cleanup of temporary experimental worlds;
- zero-pollution verification;
- reporting results through GitHub.

It does **not** autonomously modify WorldOS source code when acceptance exposes a defect. It reports the defect and waits for a new source version/task instruction.

## GitHub as the Agent Control Plane

Use GitHub as the durable communication channel between agents:

- **Issue** = Task Contract
- **Issue comment** = execution status, evidence, result, failure, or follow-up instruction
- **Issue label** = task state/routing metadata
- **Commit / Pull Request** = source changes
- **GitHub Actions** = CI and image build evidence
- **Local machine** = implementation/test execution environment
- **VPS** = production execution environment

Runtime reports should normally be Issue comments rather than committed report files. Do not pollute source history with transient deployment logs unless a report is intentionally part of permanent project documentation.

## Task Routing

Implementation work normally uses:

- `agent:local-dev`
- `status:ready`

Production deployment/E2E work normally uses:

- `agent:vps`
- `status:ready`

Do not route the same task simultaneously to multiple accountable executors unless the Architect Agent explicitly defines coordinated subtasks.

## Task State Machine

Canonical terminal/general states:

- `READY`
- `RUNNING`
- `BLOCKED`
- `FAILED`
- `PASSED`
- `CANCELLED`

Local-development handoff may additionally use:

- `LOCAL_TESTED`
- `REVIEW`
- `CHANGES_REQUESTED`

When labels are available, prefer corresponding `status:*` labels. Every agent status comment starts with `STATUS: <STATE>`.

## Required Task Contract

Every routed task must specify enough information for its executor to act safely. Development tasks should include goal/non-goals, architecture constraints, base ref, required behavior/API, determinism/compatibility requirements, tests, forbidden shortcuts, and definition of done. Deployment tasks additionally pin target commit/image, production safety boundaries, acceptance criteria, cleanup, and report shape.

If material information cannot be inferred safely, the executor must not guess. It reports `STATUS: BLOCKED` with the missing contract detail.

## Instruction Precedence

For a single Task Issue, the latest explicit Architect instruction supersedes older task details where they conflict.

The following invariants cannot be silently removed by a routine follow-up:

- no secret disclosure;
- no unauthorized mutation of real production worlds;
- no direct production SQLite mutation;
- no bypass of event sourcing;
- no bypass of optimistic concurrency;
- no bypass of idempotency;
- no weakening of causal guards merely to obtain a desired result;
- no unauthorized infrastructure changes.

Material relaxation requires explicit Human Owner approval.

## Development Safety Defaults

The Local Development Agent:

- never implements directly on `main`;
- uses an isolated branch/worktree;
- does not overwrite unrelated local changes;
- does not access production credentials;
- does not deploy production;
- does not weaken/delete/skip tests merely to make them pass;
- does not introduce unseeded randomness or unstable ordering into deterministic outputs;
- keeps changes scoped to the Task Contract;
- reports exact local test commands/results before review.

Detailed rules are in `docs/operations/local-development-agent-protocol.md`.

## Production Safety Defaults

Unless a Task Contract explicitly authorizes otherwise, do not modify:

- `First Living World`;
- `临安新镇`.

Do not:

- directly `INSERT`, `UPDATE`, or `DELETE` production SQLite state;
- delete production world databases;
- delete `control_commands.db`;
- regenerate production tokens;
- print tokens in logs or reports;
- commit secrets to Git;
- modify Caddy, Cloudflare, edge networks, or proxy aliases;
- deploy an unspecified image;
- fall back to `latest`;
- force-recreate the production proxy without explicit authorization;
- rewrite historical events;
- bypass MCP/Control APIs for production writes.

Acceptance experiments use temporary worlds/timelines by default.

## Secret Handling

Production credentials remain in VPS-local secure configuration such as `/opt/worldos/.env`.

Never place raw `WORLDOS_DEBUG_TOKEN`, `WORLDOS_CONTROL_TOKEN`, `WORLDOS_MCP_TOKEN`, or other production credentials in Issues, comments, PRs, commits, CI logs, local-agent context, or reports.

Safe report fields include `tokens_unchanged: true`, `tokens_separate: true`, and `tokens_leaked: false`. Refer to secrets by environment-variable name only.

## Deployment Rules

Deployment tasks pin both source and artifact identity. The VPS Agent verifies the requested commit and image and never silently substitutes `latest` or another SHA.

If a requested image is unavailable, report `STATUS: BLOCKED` with `REASON: IMAGE_NOT_PUBLISHED`.

Before deployment, capture the protected-world baseline: tick, event count, and world hash. Recheck them after deployment/acceptance.

## Experimental Acceptance Rules

Default acceptance lifecycle:

`create temporary world -> establish baseline -> branch -> intervention -> symmetric execution -> collect evidence -> cleanup -> zero-pollution check`

For causal experiments, verify before treatment whenever applicable:

- physical-state equivalence;
- seed equivalence;
- lineage/checkpoint equivalence;
- declared treatment difference;
- absence of unexpected differences.

Never report observational divergence as causal attribution when equivalence checks fail.

## Idempotency and Concurrency

Every normal public write uses a unique idempotency key. Reuse a key only when replay/conflict behavior is the explicit test target.

After a timeout or uncertain response, query command status before retrying a write.

Operations requiring expected hashes must refresh the target timeline hash first. A real unexpected 409 is not automatically overridden; classify it as either an intentional stale-hash test or a genuine concurrency conflict.

## Failure Protocol

When local implementation or production acceptance exposes a defect, stop expanding the failing scope and preserve the smallest useful reproduction/evidence.

Report expected vs actual behavior, relevant world/timeline or local reproduction, files/functions, tests, error, suspected area, impact, and whether protected worlds remain unchanged where applicable.

Use `STATUS: FAILED` for a demonstrated implementation/acceptance failure and `STATUS: BLOCKED` for missing prerequisites, permissions, artifacts, or ambiguous instructions.

Source fixes flow back through `agent:local-dev`; production execution remains with `agent:vps`.

## Resume Protocol

A failed or blocked task resumes only after a new explicit instruction such as `ACTION: RESUME` or renewed `STATUS: READY` with required context/version.

Do not repeat expensive steps already proven unaffected unless the new version could invalidate them.

## Reporting Contract

Reports must contain auditable evidence rather than bare PASS statements. Prefer commits, image/digest identities, exact test commands/results, ticks, event counts, hash/fingerprint prefixes, event types, timeline IDs, actors, metrics, determinism checks, idempotency checks, cleanup, and zero-pollution/security evidence as appropriate to the role.

## Cleanup

Local agents clean temporary local artifacts/worktrees when safe and never commit caches, virtual environments, local DBs, or test artifacts.

VPS agents delete temporary acceptance worlds after successful acceptance through supported APIs, never by deleting database files.

## Human Approval Gates

Stop for explicit Human Owner approval before:

1. destructive or irreversible mutation of real production worlds;
2. production token rotation;
3. major infrastructure changes;
4. irreversible/high-risk data migration;
5. reducing security controls;
6. materially expanding beyond the current approved phase;
7. any Task Contract explicitly marked `USER APPROVAL REQUIRED`.

## Multi-Agent Scaling

Agents have non-overlapping authority by default:

- Architect Agent: architecture, task contracts, review, acceptance interpretation;
- Local Development Agent: code + local tests;
- QA/experiment agent (future): protocol/test design and evidence review;
- VPS Agent: deployment + production E2E;
- operations agent (future): infrastructure only when explicitly delegated;
- research/product agent (future): specifications/analysis, no production writes by default.

Each task has one accountable executor. Agents communicate through durable GitHub artifacts rather than hidden assumptions or human copy/paste relays.

## Polling

A Local Development worker may poll for `agent:local-dev` + `status:ready`. A VPS worker may poll for `agent:vps` + `status:ready`. If continuous polling is unavailable, each checks its queue whenever invoked.

Never rerun `PASSED` or `CANCELLED` tasks. GitHub unavailability is a stop condition for new work from stale cached instructions.
