---
name: deliver
description: Deliver one coding goal end to end with compound engineering, durable goal documentation, worktree-isolated PR lanes, verification, PR maintenance, and closeout.
argument-hint: "<prompt> | resume <goal-slug>"
disable-model-invocation: true
---

# Deliver

Run the compound-engineering workflow for:

```text
$ARGUMENTS
```

This skill can edit code, create worktrees and branches, commit, push, open and
maintain PRs, enable authorized auto-merge, and close a delivery. It must be
invoked explicitly by the user.

## Invariants

1. Read `${CLAUDE_PROJECT_DIR}/docs/ai-delivery-sop.md`.
2. Keep this Claude Code session as the only code writer. Do not delegate
   critical-path implementation to another agent or session.
3. Use `docs/evolutions/<goal-slug>.md` as durable state and update it before
   lane switches, commits, pushes, waits, compaction, or completion.
4. Read repository instructions, `docs/repository-map.md`, contribution docs,
   and CI before planning.
5. Use one worktree per independent PR lane. Only background verification may
   overlap.
6. Use `make check` as the full verification entrypoint.
7. Never force-push, bypass protection or hooks, self-approve, overwrite user
   work, or destructively restore an active lane.

## Start or resume

For `resume <goal-slug>`:

1. read the goal document completely;
2. compare each lane checkpoint with Git;
3. refresh PR, CI, and review facts;
4. correct stale state;
5. continue from `Next action`.

For a new prompt:

1. create a repository-safe prompt record;
2. derive a stable goal slug;
3. create the goal document from the SOP contract;
4. inspect the repository before proposing changes.

## Plan

Record:

- definition of done and independently verifiable acceptance criteria;
- scope, out-of-scope work, and constraints;
- impacted modules and canonical docs;
- reviewer-coherent PR dependency DAG;
- worktree lanes for independent nodes;
- risks, blockers, and auto-merge authorization.

Do not parallelize a real dependency.

## Execute

For each ready lane:

1. create or enter its worktree and branch;
2. checkpoint before editing;
3. implement one coherent slice with tests and canonical docs;
4. update acceptance coverage, decisions, and friction;
5. run scoped checks and background long checks when useful;
6. checkpoint before switching lanes;
7. run `make check`;
8. self-review the complete diff;
9. record verification receipts.

On every return to a lane, read and verify its checkpoint first.

## Compound review

At every PR boundary:

- reusable judgment updates the SOP or Repository Map;
- repeated procedure updates this skill;
- deterministic policy updates the hook or CI;
- verification drift updates Make targets;
- one-off details remain in the goal document.

Apply the smallest justified delta and verify it against this delivery plus an
unrelated fixture. Otherwise record a concrete no-change reason.

## PR lifecycle

Before push:

1. update the goal document and metrics;
2. populate lane, next action, verification, friction, and infrastructure
   delta;
3. run the pre-push policy hook;
4. create repository-compliant commits;
5. push without force;
6. create or update the PR from the repository template.

Use this same session to monitor checks and comments, validate failures, make
scoped fixes, update receipts, and rerun checks. Background watchers may run
while work proceeds in another independent lane.

Enable auto-merge only when authorization is recorded and every SOP condition
holds. After merge, record the result, synchronize affected lanes
non-destructively, and advance the DAG.

## Closeout

After functional PRs merge:

1. run acceptance checks against the integrated default branch;
2. reconcile decisions and friction;
3. compute lead time, PR count, CI reruns, rework cycles, review-fix cycles,
   and retained infrastructure improvements;
4. update the delivery record and canonical docs;
5. merge a closeout PR when required;
6. verify the default branch again;
7. mark `DELIVERED`.

Only claim completion when the goal document, merged PRs, and verification
agree.

## Blocked

Record `BLOCKED`, the exact reason, and the recovery action for definitive
authentication, authorization, human-approval, destructive-ambiguity,
user-work-collision, or missing-verification failures.
