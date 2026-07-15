# Goal

- Goal document: <!-- docs/evolutions/<goal>.md -->
- Acceptance criteria covered:
  - <!-- Copy the exact criteria this slice proves. -->
- Worktree lane: <!-- lane id and branch -->
- Depends on: <!-- PR URL, branch, or "none" -->
- Base PR: <!-- PR URL or "{{DEFAULT_BRANCH}}" -->

# Change

## What

<!-- One or two sentences describing the change. -->

## Why

<!-- The problem or need. Link an issue when available. -->

# Verification

- Command: `make check`
- Result: <!-- PASS with a short receipt or CI URL -->
- Additional scoped checks:
  - <!-- command and result -->

# Compound engineering

- Friction found:
  - <!-- Link to classified goal-document entries. -->
- Infrastructure delta:
  - <!-- SOP, Skill, Hook, Map, verification, or "No change". -->
- No-change justification:
  - <!-- Required when no shared infrastructure changed. -->
- Metrics delta:
  - CI reruns:
  - Rework cycles:
  - Review-fix cycles:
  - Retained infrastructure improvements:

---

- [ ] Goal document and lane checkpoint are current
- [ ] Acceptance criteria and canonical docs changed with behavior
- [ ] `make check` passes and has a recorded receipt
- [ ] Friction has a retained delta or a concrete no-change reason
- [ ] Repository commit, privacy, language, and review policies are satisfied
