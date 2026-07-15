# Goal: Compound Engineering Harness

Goal: compound-engineering-harness
Status: BLOCKED
Started: 2026-07-15T20:56:00+08:00
Updated: 2026-07-15T21:34:00+08:00
Current PR: https://github.com/GouBuliya/personal-model/pull/1
Current lane: bootstrap
Next action: Resolve the pre-existing repository language-gate violations, then rerun make check.
Auto-merge: authorized

## Prompt record

The source discussion was not copied verbatim because this repository requires
English human-authored documentation. The policy-safe brief is:

> Establish compound engineering so every AI coding delivery improves both the
> product and the repository infrastructure. Use a delivery SOP, Claude Code
> skill, pre-push policy hook, worktree-isolated single-session workflow, PR
> template, unified verification command, Repository Map, portable bootstrap,
> and lightweight metrics.

## Definition of done

The repository contains a documented and tested compound-engineering workflow
that a single Claude Code session can use from prompt intake through a
worktree-isolated PR delivery and documented closeout, and the workflow can be
bootstrapped safely into another Git repository.

## Acceptance criteria

- [x] The SOP defines durable goal state, compound review, worktree lanes, PR
      delivery, auto-merge guards, closeout, and metrics.
- [x] Claude Code discovers a manually invoked `/deliver` skill that follows
      the SOP without delegating critical-path code writing.
- [x] The pre-push hook blocks direct default-branch pushes and stale or
      malformed delivery goal documents.
- [x] `make check` matches the repository's required offline gate, and CI uses
      the same Make targets.
- [x] The PR template links the goal, acceptance criteria, verification,
      worktree lane, dependency, and compound-engineering delta.
- [x] The Repository Map describes ownership, documentation, dependencies,
      verification, and PR boundaries.
- [x] The bootstrap preview and apply modes are idempotent and preserve local
      changes.
- [ ] Focused tests and the repository quality gate pass.

## Scope

- Repository-side AI coding delivery infrastructure.
- One Claude Code session with one active code writer.
- Multiple worktrees for independent PR lanes and overlapping background
  verification.
- GitHub PR delivery through existing `git` and `gh` tools.
- Portable templates for arbitrary-language Git repositories.

Out of scope:

- A daemon, agent SDK wrapper, database, evaluation platform, or new runtime
  package.
- Multiple coding agents writing in parallel.
- Bypassing repository review, hooks, CI, or branch protection.

## Constraints

- Preserve the current checkout's unrelated uncommitted work.
- Implement in an isolated worktree from `main`.
- Keep repository-authored content English and synthetic, except for the
  explicitly allowlisted Chinese PR collaboration templates.
- Do not commit, push, or create a PR without a separate explicit request.
- Keep `persome-core` runtime behavior unchanged.

## Repository map impact

- Add developer infrastructure under `.claude/`, `.githooks/`, `docs/`,
  `templates/`, and `scripts/`.
- Update the existing CI and PR contribution surfaces.
- Add no dependency from `src/persome/` to the delivery infrastructure.

## PR dependency DAG

1. `core`: SOP, skill, policy hook, and goal contract.
2. `support`: verification entrypoint, PR template, Repository Map, bootstrap,
   CI integration, and metrics. Depends on `core`.
3. `verification`: focused tests and final receipts. Depends on `support`.

This bootstrap implementation uses one isolated feature worktree because the
delivery skill does not exist until the first slice is complete. Future goals
use the worktree lane protocol directly.

## Worktree lanes

### bootstrap

- Worktree: `personal-model-subevolution-harness`
- Branch: `feat/subevolution-harness`
- Base: `main`
- Slice: core and support bootstrap
- State: implementation complete, with no unrelated user changes
- Verification: focused and full offline tests pass; language gate is blocked
- Blocker: three pre-existing committed documents violate the English-only gate
- Next action: resolve the baseline language violations and rerun `make check`

## Decision log

- Use a tracked Markdown goal document instead of a runtime state database.
- Use one Claude Code session; worktrees isolate lanes and background checks.
- Use Make because it is already available on supported development systems
  and adds no repository package dependency.
- Store metrics per goal to avoid a central mutable ledger and parallel merge
  conflicts.
- Bootstrap safely through templates plus a standard-library Python renderer.
- Use Chinese by default in both the repository PR template and the portable
  bootstrap template, with narrow language-gate allowlisting for those files.

## Friction ledger

### F1: Repository commands are repeated across docs and CI

- Classification: procedure
- Evidence: test, lint, scan, and documentation commands are duplicated across
  contribution instructions and workflow steps.
- Disposition: add composable Make targets and call them from CI.

### F2: Local hooks are easy to install incorrectly

- Classification: knowledge
- Evidence: tracked hooks require an explicit `core.hooksPath` setup.
- Disposition: document one-time setup and never mutate Git configuration from
  automation.

### F3: Portable templates can overwrite local policy

- Classification: invariant
- Evidence: target repositories may already own Makefiles, PR templates, or CI.
- Disposition: bootstrap must preview, hash installed files, update only
  unchanged generated files, and report conflicts.

### F4: The documented language gate is not green on the baseline

- Classification: covered
- Evidence: `docs/api-pitfalls.md`, `docs/data-driven-iteration.md`, and
  `docs/design-philosophy-intent.md` contain pre-existing CJK prose.
- Disposition: report the blocker without expanding this infrastructure change
  into an unrelated documentation translation.

### F5: PR collaboration language differs from repository source language

- Classification: policy
- Evidence: contributors need Chinese PR prompts while source, prompts, and
  durable documentation remain English.
- Disposition: use Chinese in the two PR templates and allowlist only their
  exact paths in the language gate.

## Compound engineering delta

- Outcome: Add a reusable SOP, delivery skill, policy hook, unified verification
  interface, Repository Map, PR contract, bootstrap template, and goal metrics.
- No-change justification: No runtime package or persistent service is needed;
  the repository artifacts are sufficient for this workflow.

## Verification receipts

### Focused harness

- Lane: bootstrap
- Command: `make check-harness`
- Result: PASS
- Timestamp: 2026-07-15T21:10:00+08:00
- Evidence: 7 focused tests passed

### Full offline suite

- Lane: bootstrap
- Command: `make test`
- Result: PASS
- Timestamp: 2026-07-15T21:16:00+08:00
- Evidence: 2160 passed and 15 deselected

### Static and policy checks

- Lane: bootstrap
- Command: `make lint shell docs secret pii`
- Result: PASS
- Timestamp: 2026-07-15T21:18:00+08:00
- Evidence: Ruff, format, shell syntax, links, secret scan, and PII scan passed

### Repository language gate

- Lane: bootstrap
- Command: `make language`
- Result: BLOCKED
- Timestamp: 2026-07-15T21:34:00+08:00
- Evidence: the two Chinese PR templates are explicitly exempted; only the
  three pre-existing committed Markdown files still contain disallowed CJK
  prose

### Chinese PR template policy

- Lane: bootstrap
- Command: `uv run pytest tests/test_language_scan.py tests/test_compound_engineering.py -q`
- Result: PASS
- Timestamp: 2026-07-15T21:34:00+08:00
- Evidence: 9 tests passed; exact-path template exemptions and bootstrap
  behavior are covered

## Metrics

- Start: 2026-07-15T20:56:00+08:00
- Delivery: blocked at repository baseline gate
- Lead time: 22 minutes to implementation-complete state
- PRs opened: 1
- PRs merged: 0
- CI reruns: 0
- Rework cycles: 1
- Review-fix cycles: 0
- Retained infrastructure improvements: 8

## Delivery record

Implementation is complete on `feat/subevolution-harness` and PR #1 is open.
Focused and full offline tests pass. The delivery remains `BLOCKED` because the
existing English-only repository gate fails on three documents outside this
change. The PR templates default to Chinese through a narrowly documented
language-policy exception.
