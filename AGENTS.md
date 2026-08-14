# WorldOS Agent Collaboration Contract

This file defines the repository-level collaboration contract for human operators, source-development agents, VPS execution agents, and future specialist agents.

## Roles

### Human Owner

The human owner is the final authority for irreversible production decisions, credential rotation, major infrastructure changes, security-policy reductions, destructive migration, and scope changes with material risk.

Routine development, CI, deployment, smoke testing, and acceptance testing should not require the human owner to manually relay instructions between agents.

### Source Development Agent

The source-development agent owns:

- architecture and implementation;
- tests and documentation;
- branches, commits, pull requests, and CI diagnosis;
- release/deployment task contracts;
- analysis of VPS execution reports;
- source fixes when production acceptance exposes implementation defects.

It must not ask the VPS agent to bypass event sourcing, optimistic concurrency, persistent idempotency, or production safety boundaries merely to make an acceptance test pass.

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
- **VPS** = production execution environment

Runtime reports should normally be Issue comments rather than committed report files. Do not pollute source history with transient deployment logs unless a report is intentionally part of permanent project documentation.

## Task State Machine

Canonical states:

- `READY`
- `RUNNING`
- `BLOCKED`
- `FAILED`
- `PASSED`
- `CANCELLED`

When labels are available, prefer:

- `agent:vps`
- `status:ready`
- `status:running`
- `status:blocked`
- `status:failed`
- `status:passed`

Every VPS status comment starts with:

`STATUS: <STATE>`

A task may also declare routing/state in its body when labels are unavailable:

`Agent: VPS`

`Status: READY`

## Required Task Contract

A VPS task must specify, at minimum:

- task purpose;
- target commit;
- target image when deployment is involved;
- environment;
- allowed actions;
- forbidden actions;
- acceptance criteria;
- cleanup requirements;
- expected report shape.

If a required field cannot be inferred safely, the VPS agent must not guess. It reports:

`STATUS: BLOCKED`

with the missing information.

## Instruction Precedence

For a single task Issue, the latest explicit source-agent instruction supersedes older task details where they conflict.

The following safety invariants cannot be silently removed by a routine follow-up comment:

- no secret disclosure;
- no unauthorized mutation of real production worlds;
- no direct production SQLite mutation;
- no bypass of event sourcing;
- no bypass of optimistic concurrency;
- no bypass of idempotency;
- no unauthorized infrastructure changes.

Material relaxation of those invariants requires explicit human-owner approval.

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

Never place raw `WORLDOS_DEBUG_TOKEN`, `WORLDOS_CONTROL_TOKEN`, or `WORLDOS_MCP_TOKEN` values in Issues, comments, PRs, commits, CI logs, or reports.

Safe report fields include:

- `tokens_unchanged: true`
- `tokens_separate: true`
- `tokens_leaked: false`

Refer to secrets by environment-variable name only.

## Deployment Rules

Deployment tasks pin both source and artifact identity.

The VPS agent must verify the requested commit and image. It must never silently substitute `latest` or another SHA.

If a requested image is unavailable, report:

`STATUS: BLOCKED`

`REASON: IMAGE_NOT_PUBLISHED`

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

When acceptance exposes an implementation defect, stop expanding the experiment and preserve the smallest useful diagnostic state.

Report:

- failed step;
- expected result;
- actual result;
- world/timeline;
- tick/event count/hash prefix;
- error;
- minimal reproduction;
- suspected area;
- production impact;
- whether protected worlds remain unchanged.

Use `STATUS: FAILED` for an implementation/acceptance failure and `STATUS: BLOCKED` for missing prerequisites, permissions, artifacts, or ambiguous instructions.

The source-development agent owns the subsequent source fix, PR, CI, merge, and updated deployment instruction.

## Resume Protocol

A failed or blocked task resumes only after a new explicit instruction such as `ACTION: RESUME` or a renewed `STATUS: READY` with the required version/instructions.

Do not repeat expensive steps already proven unaffected unless the new source version could invalidate them.

## Reporting Contract

A final successful VPS comment begins with:

`STATUS: PASSED`

and includes auditable evidence, preferably numeric or identity-based: commit/image/digest, ticks, event counts, hash prefixes, event types, timeline IDs, actors, metrics, determinism checks, idempotency checks, cleanup, protected-world zero-pollution, and security checks.

A bare `PASS` is insufficient.

## Cleanup

Delete temporary acceptance worlds after successful acceptance through supported APIs, never by deleting database files.

A failed temporary world may be retained only when it has diagnostic value. Report its ID and reason, then clean it after the defect is resolved.

## Human Approval Gates

Stop for explicit human-owner approval before:

1. destructive or irreversible mutation of real production worlds;
2. production token rotation;
3. major infrastructure changes;
4. irreversible/high-risk data migration;
5. reducing security controls;
6. materially expanding beyond the current approved phase;
7. any Task Contract explicitly marked `USER APPROVAL REQUIRED`.

## Multi-Agent Scaling

Future specialist agents should follow the same control-plane model and have non-overlapping authority. Examples:

- source/architecture agent: code and PRs;
- QA/experiment agent: test protocol design and evidence review;
- VPS agent: production execution only;
- operations agent: infrastructure only when explicitly delegated;
- research/product agent: specifications and analysis, no production writes by default.

Each task should have one accountable executor. Agents communicate through durable GitHub artifacts rather than hidden assumptions or human copy/paste relays.

## Continuous Polling

A VPS worker may poll for `agent:vps` + `status:ready` tasks every 1–5 minutes. If continuous polling is unavailable, it checks the task queue whenever invoked.

Never rerun `PASSED` or `CANCELLED` tasks.

GitHub unavailability is a stop condition for new production changes: do not execute new work from stale cached instructions.
