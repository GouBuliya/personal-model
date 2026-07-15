# Claude Code orientation

Read and follow [`AGENTS.md`](AGENTS.md). It is the single agent orientation for
this repository: Runtime boundary, commands, architecture, invariants, current
documentation, privacy rules, and DCO workflow.

Code is the source of truth. Keep behavior and its canonical document in the
same change, and run the full offline, lint, and PII gates before merging.

For prompt-to-PR compound engineering, invoke `/deliver` and follow
[`docs/ai-delivery-sop.md`](docs/ai-delivery-sop.md). Use
[`docs/repository-map.md`](docs/repository-map.md) to split PR lanes, keep goal
state in `docs/evolutions/<goal>.md`, and run `make check`.
