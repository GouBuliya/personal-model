# Goal

- Goal document: <!-- docs/evolutions/<goal>.md -->
- Acceptance criteria covered:
  - <!-- Copy the exact criteria this slice proves. -->
- Worktree lane: <!-- lane id and branch -->
- Depends on: <!-- PR URL, branch, or "none" -->
- Base PR: <!-- PR URL or "main" -->

# Change

## What

<!-- One or two sentences: what does this PR change? -->

## Why

<!-- The problem or need. Link issues: Fixes #123 -->

# How verified

- Command: `make check`
- Result: <!-- PASS with a short receipt or CI URL -->
- Additional scoped checks:
  - <!-- command + result -->

# Compound engineering

- Friction found:
  - <!-- Link each item to its classification in the goal document. -->
- Infrastructure delta:
  - <!-- SOP, Skill, Hook, Repository Map, verification, or "No change". -->
- No-change justification:
  - <!-- Required when no shared infrastructure changed. -->
- Metrics delta:
  - CI reruns:
  - Rework cycles:
  - Review-fix cycles:
  - Retained infrastructure improvements:

---

- [ ] Goal document is current and contains this lane's checkpoint
- [ ] Acceptance criteria and canonical documentation changed with behavior
- [ ] `make check` passes and the receipt is recorded in the goal document
- [ ] Compound-engineering friction is classified with a retained delta or reason
- [ ] Commits are signed off (`git commit -s`) — DCO required, see CONTRIBUTING.md
- [ ] No real names / emails / tokens in code or test fixtures (synthetic data only)
- [ ] Secret scan passes (`scripts/secret_scan.py`)
- [ ] Human-authored repository text is English (`scripts/language_scan.py` passes)
