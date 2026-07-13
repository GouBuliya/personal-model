# Persome Formation & Retrieval Upgrade — Report

Outcome ledger for the mechanisms in `docs/memory-formation-upgrade.md`, in the
format of the owner's research lab (`agent-memory-lab/docs/ledger.md`). Each row:
mechanism → status (shipped / default-off / deferred / rejected) → public anchor
→ how it was verified.

Discipline note (spec §3): the frozen golden fixture
(`tests/fixtures/formation_golden/`) is a **formation-domain** proxy — it scores
extraction precision/recall/calendar/polarity on one persome screen session. It
does **not** score retrieval ranking. So the retrieval heads (C2–C4) cannot earn
their inclusion here; per the lab's own "don't ship an unvalidated mechanism"
rule, they are recorded as deferred to a retrieval-benchmark round, not shipped
default-on.

## Batch A — formation prompt + gate

| Mechanism | Status | Anchor | Verification |
|---|---|---|---|
| A1 authored-evidence gate | **shipped** | HaluMem interference, arXiv 2511.03506 | `gate_delta` checks quotes against assistant/system/preview-stripped `evidence_text`; entity existence still uses full text. Tests: `test_evidence_text_strips_assistant_and_preview_spans`, `test_assistant_output_quote_cannot_ground_an_assertion`. |
| A2 dense self-contained narrative | **shipped (prompt)** | MemOS mem_reader; Structurally Aligned Subtask-Level Memory, OpenReview 2CoRS45Ucj | Density rule added to `memory_delta.md`. Prompt-driven; measured by the opt-in live pass on the fixture (not a deterministic gate). |
| A3 calendar anchoring | **shipped** | MemOS reader; APEX-MEM arXiv 2604.14362 | `<session_date>` injected into the formation context; prompt resolves relative times to absolute dates. Prompt-driven. |
| A4 polarity fidelity | **shipped** | HaluMem interference, arXiv 2511.03506 | Assertions now carry normalized `polarity`; declined/stopped stances stored as stance. Tests: `test_authored_quote_grounds_an_assertion_with_polarity`, `test_assertion_polarity_is_preserved_and_normalized`, `test_invalid_assertion_polarity_falls_back_to_neutral`. |

## Batch B — sampling & completeness

| Mechanism | Status | Anchor | Verification |
|---|---|---|---|
| B1 completeness re-read (pass 2) | **shipped, default-off** (`[memory_delta] completeness_reread`) | ProMem, arXiv 2601.04463 | Second pass over the same window with pass-1 memories as prior; admits only missed items; cross-pass dedup; a failed re-read never loses pass 1. Test: `test_completeness_reread_admits_only_missed_facts`. Default-off: doubles per-window LLM cost; the primary recall lever, to be turned on and measured on the live fixture / retrieval benchmark. |
| B2 temperature-decorrelated dual-sample | **shipped, default-off** (`[memory_delta] decorrelated_samples`) | self-consistency, Wang et al. 2022 | Samples T=0 then T=0.7, unions candidates before gating, keeps the supersession-carrying candidate on collision. Tests: `test_decorrelated_second_sample_uses_positive_temperature`, `test_union_raw_dedups_and_keeps_supersession_candidate`. Default-off: doubles cost. |

## Batch C — facets & retrieval heads

| Mechanism | Status | Anchor | Verification / rationale |
|---|---|---|---|
| C1 facet capture (formation side) | **shipped** | MemGAS, ICLR 2026 / arXiv 2505.19549 | Assertions/events carry an optional `facets` list, gated to ≤6 short deduped handles, addressing-only (never surfaced as facts — the dense `text` stands alone). Persisted in the `memory_deltas` payload. Tests: `test_facets_are_captured_normalized_and_capped`, `test_missing_or_bad_facets_yield_empty_list`. |
| C1 facet index/head (retrieval side) | **deferred** | MemGAS | Wiring a facet pool into `store/fts.py`/`retrieval/associative.py` cannot be validated on the formation fixture (no retrieval scoring), and the retrieval path was just stabilized under the single-owner EXCLUSIVE contract (d59cb47). Deferred to a retrieval-benchmark round (feed persome formation output to the lab's OmniMemEval harness). Facets are already captured (C1 above), so the index has its source when that round runs. |
| C3 temporal-decay head | **deferred** | SYNAPSE, arXiv 2601.02744 | Same rationale — needs a retrieval benchmark to earn inclusion; a persome recency-decay pool already exists in `_bm25_pool`/window scoring, so the marginal head must prove additive gain, which the formation fixture cannot show. |
| C4 association (Hebbian) head | **deferred** | HeLa-Mem arXiv 2604.16839 + SYNAPSE lateral inhibition | Same rationale. persome already has a relation/slot pool; a co-formation Hebbian head must prove gain over it on a retrieval benchmark. |

## Excluded — DISCARDED by the lab's paired gate (not ported)

| Mechanism | Anchor | Action taken |
|---|---|---|
| MMR retrieval diversity | Skill2Mem negative transfer | `vector_recall_diversity_lambda` kept default **0.0 (off)**; documented as known-ineffective. Not enabled anywhere. |
| Surprise/state-transition gating | Titans/MIRAS (lab M2-R1 FAIL) | Not ported. |
| Standalone dense head add-on | lab M3-R1 (orthogonal noise) | Not ported. |
| Entropy-based dynamic head weights | — | Not ported. |
| Episode grouping (seed→siblings) | — | Not ported. |

## Gates

- Full offline suite `PERSOME_LLM_MOCK=1 uv run pytest -m "not macos and not integration"`: all pass.
- `ruff check` / `ruff format --check`: clean.
- `secret_scan.py` / `pii_scan.py` / `language_scan.py`: clean.
- Commits: Batch A `feat(formation): Batch A …`, Batch B `feat(formation): Batch B …`, Batch C `feat(formation): Batch C1 …` — each `-s`, each citing its public anchor.

## Next round (independent, not blocking)

Turn on B1 (and optionally B2) and run the live formation pass on the fixture to
quantify the recall gain; then wire the deferred retrieval heads (C1-index, C3,
C4) and validate them against the lab's OmniMemEval retrieval protocol — the
"harder signal" round flagged in the spec's reminders. That is where a retrieval
head either earns its weight or is recorded as rejected.
