# {{PROJECT_NAME}} Repository Map

## Purpose

Use this map to assign reviewers, update canonical documentation, respect
dependency boundaries, select verification, and split delivery PRs.

Update this file whenever a delivery reveals stale ownership or architecture
information.

## System flow

Describe the main production flow:

```text
input -> normalization -> domain logic -> persistence -> public surface
```

## Modules

For each module, record:

```text
### Module name

- Paths:
- Responsibility:
- Reviewer role:
- Canonical docs:
- Allowed dependencies:
- Forbidden dependencies:
- Verification:
- Natural PR boundary:
```

## Shared contracts

Record schemas, generated artifacts, public APIs, database contracts, prompts,
and other files that require source and generated outputs to move together.

## PR DAG rules

1. Map every acceptance criterion to its owning module.
2. Keep behavior, tests, and canonical docs in one PR node.
3. Split independent ownership or risk boundaries.
4. Add edges for foundations consumed by later nodes.
5. Keep generated artifacts with their source.
6. Do not parallelize nodes that write the same contract.
7. Allocate independent nodes to separate worktrees.
8. Re-run downstream verification after an integrated dependency changes.

## Verification map

- Full repository gate: `make check`
- Default branch: `{{DEFAULT_BRANCH}}`
- Add focused commands by module:
  - Module:
  - Command:
  - Evidence:
