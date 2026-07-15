# Compound Engineering Delivery SOP

## Purpose

This SOP turns one coding prompt into an auditable delivery while improving the
repository's ability to deliver the next change. A delivery has two outputs:

1. the requested product change; and
2. a justified improvement to reusable engineering knowledge, automation, or
   enforcement.

The workflow is designed for one Claude Code session. Git worktrees isolate PR
lanes and let background verification overlap, but only one agent writes code.

## Source of truth

Every delivery owns one tracked goal document:

```text
docs/evolutions/<goal-slug>.md
```

Conversation history is useful context, not durable state. The goal document
wins when a resumed or compacted conversation disagrees with it. Read the goal
document and verify its Git and GitHub facts before resuming work.

Repository privacy and language rules take precedence over verbatim prompt
storage. If the original prompt cannot be committed safely, record:

- a policy-compliant brief;
- why the original was omitted;
- a stable digest or external issue reference when available.

Never commit secrets, private captures, raw model reasoning, or transcripts.

## Required goal document contract

Use these top-level fields:

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

Use these headings:

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

Do not leave `TBD`, `TODO`, placeholder angle brackets, or unchecked acceptance
criteria in a document used to open or update a PR.

### Worktree lane checkpoint

Before leaving a lane, record:

- lane id and worktree path;
- branch and base commit;
- owning PR slice and dependency;
- dirty or clean state;
- completed work;
- verification running or completed;
- blocker, if any;
- exact next action.

On entering a lane, compare the checkpoint with `git status`, the current
branch, and the current base before editing.

### Friction ledger

Record concrete friction as it happens. At each PR boundary, classify every
entry:

- `knowledge`: reusable judgment or repository knowledge;
- `procedure`: a repeated sequence suitable for a skill;
- `invariant`: a deterministic rule suitable for a hook or CI check;
- `one-off`: task-specific detail that should not enter shared infrastructure;
- `covered`: already handled by existing infrastructure.

### Compound engineering delta

Map retained friction to the smallest durable surface:

- reusable knowledge or judgment updates this SOP or the Repository Map;
- a repeated executable procedure updates the delivery skill;
- a deterministic invariant updates the pre-push hook or CI;
- verification command drift updates the Make targets;
- a one-off remains only in the goal document.

Infrastructure churn is not a success criterion. `No change` is valid only when
the goal document explains why each friction item is `one-off` or `covered`.
Verify an infrastructure change against the motivating delivery and at least
one unrelated fixture.

### Verification receipt

Each receipt records:

```text
- Lane: <lane id>
- Command: <exact command>
- Result: PASS | FAIL | BLOCKED
- Timestamp: <ISO-8601 timestamp>
- Evidence: <short result, artifact path, or CI URL>
```

Do not claim a check ran when the evidence is only an agent statement.

### Metrics

Record lightweight delivery metrics in the goal document:

- start and delivery timestamps;
- lead time;
- PRs opened and merged;
- CI reruns;
- implementation rework cycles;
- review-fix cycles;
- retained SOP, skill, hook, Repository Map, and verification improvements.

Use the same definitions across goals. A CI rerun is a new run after a failed
or cancelled run. A rework cycle is a code change required because a completed
slice did not satisfy its acceptance criteria.

## Delivery procedure

### 1. Intake and preflight

1. Read `AGENTS.md`, `CLAUDE.md`, the Repository Map, README, contribution
   guidance, and CI configuration.
2. Check the working tree, default branch, remotes, GitHub authentication,
   required reviews, auto-merge availability, commit sign-off policy, and local
   verification command.
3. Create or resume the goal document.
4. Record missing credentials, permissions, or product choices as `BLOCKED`.
   Do not improvise around them.

### 2. Define delivery

1. Normalize the prompt into a concrete definition of done.
2. Derive independently verifiable acceptance criteria.
3. State scope, out-of-scope work, and hard constraints.
4. Identify canonical documents that must change with behavior.
5. Identify expected compound-engineering opportunities without precommitting
   to unnecessary infrastructure changes.

### 3. Plan the PR dependency DAG

Split work by reviewer concern and real dependency:

- keep tightly coupled behavior, tests, and canonical docs together;
- separate independent ownership or risk boundaries;
- put foundations before consumers;
- make every slice independently reviewable against named acceptance criteria;
- mark each edge in the dependency DAG.

Independent nodes may occupy worktrees concurrently. Dependent nodes must wait
for their predecessor to merge unless the repository explicitly permits a
stacked-branch workflow.

### 4. Allocate worktree lanes

Use one branch and one worktree per independent PR slice. Prefer branch names:

```text
deliver/<goal-slug>/<lane>-<slice>
```

Only the main Claude Code session writes. It may:

- launch tests, builds, or CI watchers in one lane;
- checkpoint that lane;
- switch to another independent lane;
- continue implementation while background verification runs.

It must not:

- start another coding agent for critical-path implementation;
- edit two lanes without checkpointing;
- treat a result from one lane as evidence for another;
- run destructive restore or cleanup in an active lane;
- parallelize slices with an unresolved dependency.

### 5. Implement a slice

For each lane:

1. verify the checkpoint and base;
2. make the smallest coherent implementation;
3. add or update tests;
4. update canonical documentation in the same slice;
5. update the goal document's decisions, friction, lane checkpoint, and
   acceptance coverage;
6. run scoped checks, then `make check`;
7. perform a focused self-review of the diff;
8. record verification receipts and compound-engineering classification.

### 6. Push and open the PR

Before pushing:

1. ensure the goal document changed with the slice;
2. ensure the current lane and PR state are accurate;
3. ensure `make check` has a passing receipt;
4. run the configured pre-push hook;
5. commit with repository-required sign-off;
6. push without force and create the PR from the repository template.

The PR must link the goal, acceptance criteria, verification receipts, worktree
lane, dependency, and compound-engineering delta.

### 7. Maintain and merge

Use the same Claude Code session to:

1. monitor required CI and review comments;
2. validate every reported issue before changing code;
3. fix only issues within the PR's scope;
4. rerun affected checks and update receipts and metrics;
5. keep the PR branch and goal document synchronized.

Enable auto-merge only when all of the following hold:

- the goal document says `Auto-merge: authorized`;
- required CI and reviews pass;
- no unresolved change request remains;
- branch protection is not bypassed;
- the slice's canonical docs and compound review are current;
- no self-approval is required.

After merge, update the goal document and synchronize remaining lanes
non-destructively. Re-run checks invalidated by the new integrated base.

### 8. Close out

After all functional PRs merge:

1. run the complete acceptance suite against integrated `main`;
2. reconcile all acceptance criteria and friction entries;
3. compute the lightweight metrics;
4. update canonical docs and the goal delivery record;
5. create a closeout PR when documentation changed after integration;
6. merge the closeout PR under the same policy;
7. mark `DELIVERED` only after final main-branch verification passes.

Remove worktrees only after their changes are merged or explicitly abandoned
and their terminal state is recorded.

## Resuming the same session

Use `/deliver resume <goal-slug>`. On resume:

1. read this SOP and the entire goal document;
2. compare every lane checkpoint with Git;
3. refresh PR and CI facts from GitHub;
4. correct stale state in the goal document;
5. continue from `Next action`.

Do not start a replacement agent merely because the context was compacted.

## Repository-local policy

This repository uses:

```text
Verification entrypoint: make check
Default branch: main
Goal documents: docs/evolutions/
Delivery branches: deliver/<goal>/<lane>-<slice>
```

Install the tracked hook once per checkout:

```bash
git config core.hooksPath .githooks
```

The repository or organization may manage hooks another way. Never change Git
configuration automatically from the skill or bootstrap process.
