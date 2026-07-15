# {{PROJECT_NAME}} Compound Engineering Delivery SOP

## Mission

Every delivery produces two outputs:

1. the requested product change; and
2. a justified improvement to the repository's future delivery capability.

Use one Claude Code session as the only code writer. Worktrees isolate
independent PR lanes and allow background verification to overlap.

## Durable goal state

Every delivery owns:

```text
docs/evolutions/<goal-slug>.md
```

The goal document is authoritative after context compaction, waiting, or
resume. Keep it current before changing worktrees, committing, pushing,
waiting, or claiming completion.

Follow repository language, privacy, and secret policy. If the original prompt
cannot be committed, store a policy-compliant brief and explain the omission.
Never commit transcripts or raw model reasoning.

## Goal contract

Required fields:

```text
Goal: <goal-slug>
Status: PLANNING | ACTIVE | WAITING | BLOCKED | READY_FOR_PR | DELIVERED
Started: <ISO-8601 timestamp>
Updated: <ISO-8601 timestamp>
Current PR: not-opened | <PR URL>
Current lane: <lane id>
Next action: <one concrete action>
Auto-merge: authorized | disabled
```

Required sections:

```text
## Prompt record
## Definition of done
## Acceptance criteria
## Scope
## Constraints
## Repository map impact
## PR dependency DAG
## Worktree lanes
## Decision log
## Friction ledger
## Compound engineering delta
## Verification receipts
## Metrics
## Delivery record
```

Before a push, remove placeholders and record at least one classified friction
entry, one compound-engineering outcome, and one passing verification receipt.

## Compound engineering

Classify observed friction at each PR boundary:

- `knowledge`: reusable judgment for the SOP or Repository Map;
- `procedure`: repeated steps for the delivery skill;
- `invariant`: deterministic policy for the hook or CI;
- `one-off`: task detail that stays in the goal document;
- `covered`: already handled by current infrastructure.

Retain the smallest useful delta. No infrastructure change is valid only with
a concrete reason for every friction item. Verify shared infrastructure against
the motivating delivery and an unrelated fixture.

## Plan the PR DAG

1. Read repository instructions, the Repository Map, contribution docs, and CI.
2. Define one verifiable outcome and acceptance criteria.
3. Identify affected modules, canonical docs, reviewers, and verification.
4. Split work by real ownership and dependency boundaries.
5. Keep behavior, tests, and canonical docs in the same node.
6. Allocate independent nodes to separate worktrees.
7. Keep dependent nodes serial unless repository policy explicitly supports a
   stacked branch.

## Worktree-driven single-session pipeline

Use branches:

```text
deliver/<goal-slug>/<lane>-<slice>
```

Only one Claude Code session writes code. It may run tests, builds, or CI
watchers in the background in one worktree, checkpoint that lane, and implement
another independent lane.

Before leaving a worktree, record:

- worktree, branch, base commit, and owning slice;
- dirty state and completed work;
- verification in flight;
- blocker and exact next action.

On entry, compare the checkpoint with Git. Never use another lane's result as
evidence. Never run destructive restore or cleanup in an active lane.

## Implement and verify

For every slice:

1. verify its checkpoint and base;
2. implement one coherent change;
3. add tests and canonical documentation;
4. update decisions, friction, acceptance coverage, and lane state;
5. run scoped checks, then `make check`;
6. self-review the full diff;
7. record exact verification receipts;
8. perform the compound-engineering review.

Receipts use:

```text
- Lane: <lane id>
- Command: <exact command>
- Result: PASS | FAIL | BLOCKED
- Timestamp: <ISO-8601 timestamp>
- Evidence: <short output, artifact, or CI URL>
```

## PR delivery

Before pushing:

1. update the goal document;
2. ensure the current lane and next action are accurate;
3. record a passing `make check` receipt;
4. run the tracked pre-push hook;
5. commit under repository policy;
6. push without force and use the PR template.

The same Claude Code session monitors CI and review, validates failures,
applies scoped fixes, updates metrics, and reruns affected checks.

Auto-merge is allowed only when:

- `Auto-merge: authorized` is recorded;
- required checks and reviews pass;
- no unresolved change request remains;
- branch protection and hooks are not bypassed;
- canonical docs and compound review are current;
- no self-approval is needed.

After merge, record the PR and merge commit, update the integrated base, and
rerun checks invalidated in remaining lanes.

## Closeout

After all functional PRs merge:

1. verify every acceptance criterion against integrated `{{DEFAULT_BRANCH}}`;
2. reconcile decisions and friction;
3. record start/delivery time, lead time, PR count, CI reruns, rework cycles,
   review-fix cycles, and retained infrastructure improvements;
4. update canonical docs and the delivery record;
5. merge a documentation closeout PR when needed;
6. verify the default branch again;
7. mark `DELIVERED`.

## Resume and block

Use `/deliver resume <goal-slug>`. Read the SOP and goal document, compare lane
state with Git, refresh PR facts, correct stale state, and continue from
`Next action`.

Record `BLOCKED` and stop for definitive authentication, authorization,
required-human-approval, destructive ambiguity, user-work collision, or missing
verification-path failures.

## Local policy

```text
Default branch: {{DEFAULT_BRANCH}}
Full verification: make check
Goal documents: docs/evolutions/
```

Install the tracked hook once per checkout:

```bash
git config core.hooksPath .githooks
```

Do not change Git configuration automatically from the skill or bootstrap.
