---
name: deliver
description: Deliver one coding goal end to end with compound engineering, durable goal documentation, worktree-isolated PR lanes, verification, PR maintenance, and closeout.
argument-hint: "<prompt> | resume <goal-slug>"
disable-model-invocation: true
---

# Deliver

Run the repository's compound-engineering delivery workflow for:

```text
$ARGUMENTS
```

This is a side-effecting workflow. It may edit code, create worktrees and
branches, commit, push, open PRs, maintain them, enable authorized auto-merge,
and close the delivery. Do not invoke it without an explicit user `/deliver`.

## Standing rules

1. Read `${CLAUDE_PROJECT_DIR}/docs/ai-delivery-sop.md` before acting.
2. Keep one Claude Code session as the only code writer. Do not use subagents,
   agent teams, routines, or replacement sessions for critical-path work.
3. Use `docs/evolutions/<goal-slug>.md` as durable state. Update it before
   changing lanes, committing, pushing, waiting, compacting, or claiming
   completion.
4. Read `AGENTS.md`, `CLAUDE.md`, `docs/repository-map.md`, README,
   contribution guidance, and CI configuration. Repository rules override this
   skill.
5. Use one worktree per independent PR lane. Only background tests, builds,
   and CI watchers may overlap; only this session writes code.
6. Use `make check` as the full verification entrypoint.
7. Never force-push, bypass branch protection, skip hooks, approve your own PR,
   overwrite user work, or run destructive restore in an active worktree.
8. Keep source, docs, fixtures, and goal records compliant with repository
   language, privacy, and synthetic-data policy.

## Start or resume

If the arguments begin with `resume`:

1. resolve the requested goal document;
2. read it completely;
3. verify every lane's branch, base, worktree, dirty state, PR, CI, and review
   facts;
4. correct stale facts in the document;
5. continue from `Next action`.

Otherwise:

1. preserve a repository-safe prompt record;
2. derive a stable lowercase goal slug;
3. create `docs/evolutions/<goal-slug>.md` using the SOP contract;
4. set `Status: PLANNING`;
5. inspect the repository before proposing implementation.

If the original prompt violates repository language, privacy, or secret rules,
commit only a policy-compliant brief and a reason the original was omitted.

## Plan

Write into the goal document:

- one verifiable definition of done;
- acceptance criteria with explicit verification;
- in-scope and out-of-scope work;
- hard constraints;
- impacted Repository Map entries and canonical docs;
- a reviewer-coherent PR dependency DAG;
- worktree lanes for independent nodes;
- expected risks and blockers;
- auto-merge authorization from the user or repository policy.

Do not parallelize a real dependency. Prefer independent PRs from the current
integrated base. If a slice depends on another, wait for the predecessor to
merge before creating its lane unless repository policy explicitly permits a
stacked branch.

## Execute lanes

For each ready DAG node:

1. create or enter its dedicated worktree and branch;
2. record the lane checkpoint before editing;
3. implement one coherent slice with tests and canonical docs;
4. update acceptance coverage, decisions, and friction;
5. run scoped verification;
6. launch long verification in the background when useful;
7. checkpoint before moving to another independent lane;
8. run `make check` before the slice is ready to push;
9. self-review the full diff and fix valid findings;
10. record exact verification receipts.

When returning to a lane, read its checkpoint first and compare it with Git.
Never infer another lane's state from memory.

## Compound review

At each PR boundary, classify every friction entry:

- reusable judgment goes to the SOP or Repository Map;
- repeated executable steps go to this skill;
- deterministic policy goes to the pre-push hook or CI;
- verification drift goes to the Make targets;
- one-off details remain in the goal document.

Apply the smallest justified infrastructure delta. Verify it against this
delivery and an unrelated fixture. If no shared artifact changes, record a
specific no-change reason for every friction item.

## PR lifecycle

Before each push:

1. ensure the goal document changed with the slice;
2. populate current PR, lane, next action, verification, friction
   classification, infrastructure delta, and metrics;
3. run the tracked pre-push policy hook;
4. create repository-compliant commits, including sign-off when required;
5. push without force;
6. create or update the PR from `.github/PULL_REQUEST_TEMPLATE.md`.

Maintain the PR in this same session:

1. monitor required checks and unresolved comments;
2. validate failures and review claims;
3. make only scoped fixes;
4. update the goal document and metrics;
5. rerun affected checks;
6. enable auto-merge only when the SOP conditions and recorded authorization
   hold.

While CI runs, use a background watcher or the session's loop capability. It is
valid to work in another independent lane after checkpointing the current lane.

After merge:

1. record the PR URL and merge commit;
2. synchronize affected lanes with integrated `main` non-destructively;
3. rerun invalidated checks;
4. advance the dependency DAG.

## Closeout

After all functional PRs merge:

1. run all acceptance checks against integrated `main`;
2. reconcile decisions and friction;
3. compute lead time, PR count, CI reruns, rework cycles, review-fix cycles,
   and retained infrastructure improvements;
4. update the final delivery record and canonical docs;
5. open and merge a closeout PR if integration produced documentation changes;
6. verify `main` again;
7. set `Status: DELIVERED`.

Only report completion when the goal document, merged PRs, and final
verification all agree.

## Blocked state

Set `Status: BLOCKED`, write the exact blocker and recovery action, and stop
when any of these occurs:

- authentication, authorization, quota, or branch policy prevents progress;
- required human approval cannot be obtained by this session;
- a destructive or product decision is genuinely ambiguous;
- user work would have to be overwritten;
- the repository cannot provide a trustworthy verification path.
