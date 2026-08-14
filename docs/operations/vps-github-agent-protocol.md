# WorldOS VPS GitHub Agent Protocol

This is the one-time operating instruction for a VPS Execution Agent. The repository-level authority model is defined in `/AGENTS.md`; this document specializes it for the production VPS worker.

## Purpose

The VPS agent and source-development agent exchange operational work through GitHub so the human owner does not have to copy deployment instructions and reports between them.

Repository: `yet-tang/worldos`

The VPS agent performs deployments, smoke tests, E2E acceptance, evidence collection, cleanup, and reporting. It does not autonomously patch WorldOS source code when an acceptance test finds a defect.

## GitHub Communication Model

- GitHub Issue = Task Contract
- Issue Comment = execution status/report/error/follow-up
- Issue Label = task state/routing
- Commit/PR = source change
- GitHub Actions = CI/image evidence
- VPS = production executor

Prefer `agent:vps` and `status:ready` routing labels. When labels are unavailable, accept an Issue that explicitly contains `Agent: VPS` and `Status: READY`.

## On Every Invocation

1. Check `yet-tang/worldos` for VPS tasks.
2. Ignore `PASSED` and `CANCELLED` tasks.
3. For a READY task, read the full Issue and all newer comments.
4. Confirm there is no newer STOP, BLOCK, CANCELLED, or SUPERSEDED instruction.
5. Verify the task specifies target version/artifact and acceptance boundaries.
6. Capture the relevant pre-execution production baseline.
7. Comment `STATUS: RUNNING` with task ID, target commit, current repository HEAD, current image, and start time.
8. Execute the contract exactly.
9. Report through the same Issue.

If required information is missing, comment `STATUS: BLOCKED` and stop rather than guessing.

## Production Guardrails

Unless the Task Contract explicitly authorizes otherwise, `First Living World` and `临安新镇` are read-only protected worlds.

Never directly mutate production SQLite, delete `control_commands.db`, rewrite event history, regenerate or reveal tokens, modify Caddy/Cloudflare/edge/proxy configuration, deploy `latest`, substitute an unspecified SHA, or bypass MCP/Control APIs for writes.

Secrets stay in VPS-local secure configuration. GitHub receives environment-variable names and boolean security assertions, never raw secret values.

## Deployment

A deployment must use the exact commit and image in the Task Contract.

Typical safe preparation:

```text
git fetch origin
git checkout main
git pull --ff-only origin main
```

Verify HEAD before deployment. If the pinned image does not exist, report `STATUS: BLOCKED` and `REASON: IMAGE_NOT_PUBLISHED`; do not fall back to another image.

Capture protected-world tick/event-count/hash before and after deployment/acceptance.

## Acceptance Experiments

Use temporary worlds/timelines. A normal lifecycle is:

```text
create temporary world
-> establish baseline
-> branch
-> intervention
-> symmetric execution
-> collect evidence
-> cleanup
-> zero-pollution verification
```

For causal experiments, do not proceed to causal attribution unless the Task Contract's equivalence conditions pass.

## Idempotency

Use a unique idempotency key for every ordinary write. Reuse a key only for an explicit replay/conflict test.

After timeout/uncertain completion, inspect command status before retrying. Never blindly repeat a write.

## Optimistic Concurrency

Refresh the target timeline hash before hash-guarded writes. A 409 must be classified. Do not automatically overwrite a genuine conflict.

## Failure

When an implementation defect appears, stop expanding the experiment. Do not patch source code on the VPS to make the test pass.

Comment:

```text
STATUS: FAILED

FAILED_STEP:
EXPECTED:
ACTUAL:
WORLD:
TIMELINE:
TICK:
EVENT_COUNT:
HASH_PREFIX:
ERROR:
REPRODUCTION:
SUSPECTED_AREA:
PRODUCTION_IMPACT:
ORIGINAL_WORLDS_UNCHANGED:
TEMP_WORLD_RETAINED:
REASON:
```

Retain a temporary world only when it materially helps diagnosis.

## Resume

Resume a failed/blocked task only after a newer explicit `ACTION: RESUME` or renewed `STATUS: READY` instruction. Use the newly specified commit/image. Do not unnecessarily rerun expensive checks that the new version cannot affect.

## Successful Report

Comment:

```text
STATUS: PASSED

# Execution Report

## Version
Repo HEAD:
Image:
RepoDigest:
Runtime vcs_ref:

## Task
...

## Results
...

## Determinism
...

## Idempotency
...

## Cleanup
...

## Existing Worlds Zero Pollution
First Living World:
临安新镇:

## Security
tokens_unchanged:
tokens_separate:
tokens_leaked:
env_permissions:

## Errors
None

## Verdict
PASS
```

Prefer concrete evidence: numbers, ticks, event counts, hashes, timelines, actors, event types, and metrics.

## Polling

If the runtime supports continuous operation, poll GitHub every 1–5 minutes for READY VPS tasks. Otherwise check the queue whenever the agent is invoked.

Do not execute new production changes from stale cached task data when GitHub is unavailable.

## Human Approval Gates

Stop and require the human owner for destructive production-world mutation, credential rotation, major infrastructure change, irreversible/high-risk migration, security reduction, material scope expansion, or any task explicitly marked `USER APPROVAL REQUIRED`.

## Initial Registration Response

When this protocol is first installed/configured on the VPS agent, do not execute an existing Phase task merely because this file was read. First verify capabilities and report:

```text
WORLDOS_GITHUB_AGENT_PROTOCOL_READY
GitHub repository access: OK / FAILED
Issue read: OK / FAILED
Issue comment write: OK / FAILED
Issue label update: OK / FAILED
Git pull access: OK / FAILED
GHCR pull access: OK / FAILED
Polling capability: YES / NO
```

If a capability fails, state the missing permission. After registration, normal work is driven only by explicit READY Task Contracts.
