# Persome Formation & Retrieval Upgrade — Spec v1

> Port the formation and retrieval mechanisms that the owner's personal research
> lab (`~/agent-memory-lab`) validated on public benchmarks (HaluMem /
> LongMemEval via OmniMemEval) into this fork's live runtime. Every mechanism
> here is drawn from that lab's ledger (`docs/ledger.md`) and SPEC (`SPEC.md`);
> each carries the same first-hand public anchor. Mechanisms the lab's paired
> gate DISCARDED are listed under §5 and must NOT be ported.

## 0. Why

The lab's honest picture (T=0 judge, `floors v2.1`): the M1 stack —
seven formation principles + a multi-head weighted-RRF bank — beats the MemOS
baseline on **weighted accuracy, update-correctness, and QA** (strict
separation), and loses only **extraction F1 by 1.65pp**, with the loss located
entirely in **integrity recall** (target-accuracy is ~0.998, near-saturated).
So the validated levers are: (a) formation-quality principles that this fork's
`memory_delta.md` does not yet encode, and (b) a small set of retrieval heads.
The bottleneck to attack is recall-without-precision-loss.

Persome extracts from **screen-activity sessions** (timeline blocks), not
chat transcripts, so the "user-authored evidence" gate maps to "authored text"
(chat messages, terminal input the owner typed) versus content an app merely
displayed. Formation-quality principles are domain-general and transfer; the
evidence gate is adapted, not copied.

## 1. Scope — three batches, all delivered in one pass

### Batch A — formation prompt (no schema/architecture change; `memory_delta.md` + gate)

Edit `src/persome/prompts/memory_delta.md` and the deterministic gate in
`src/persome/writer/memory_delta.py` / `delta_apply.py`:

- **A1 · Authored-evidence gate** — a `quote` may only ground an item when it is
  text the OWNER authored (typed/sent), not text an app or an assistant merely
  displayed. Assistant/counterparty lines are context, never evidence. (HaluMem
  interference design, arXiv 2511.03506.) Persome mapping: prefer quotes from
  `focused_value` / owner-authored timeline text; when the evidence form is
  ambiguous, keep the confidence floor as the backstop and label the source.
- **A2 · Dense self-contained narrative** — each assertion/event is ONE complete
  sentence packing every explicit detail present (who/what/when/where/how much/
  with whom/why); completeness over brevity. Do NOT shatter a compound fact into
  fragment atoms (fragments hurt QA and waste retrieval budget). (MemOS
  `mem_reader_prompts.py`; Structurally Aligned Subtask-Level Memory, OpenReview
  2CoRS45Ucj.)
- **A3 · Calendar anchoring** — resolve every relative time ("yesterday"/"next month") to an
  absolute date; distinguish event time from mention time; annotate approximate
  when unsure. (MemOS reader; APEX-MEM arXiv 2604.14362.) A `now`/session-date
  anchor must be injected into the prompt context.
- **A4 · Polarity fidelity** — options the owner *considered but did not choose*,
  or *used to do and stopped*, enter memory only with explicit stance wording,
  never as established fact; options an assistant proposed but the owner did not
  adopt are excluded entirely. Extend the existing `polarity` beyond relations to
  assertions. (HaluMem interference, arXiv 2511.03506.)

### Batch B — formation sampling & completeness (small code; `writer/agent.py`, `memory_delta.py`)

- **B1 · Completeness re-read (pass 2)** — after pass 1 admits its delta, call the
  model a second time over the SAME window with all pass-1 admitted memories in
  `prior`; admit ONLY owner-authored facts pass 1 missed; if the window later
  revised a fact, emit only the final state. Cross-pass dedup by
  `(kind, normalized content)`. Config-gated (`[memory_delta] completeness_reread`,
  default off), env-injected per run so shared env never silently carries it.
  (ProMem active re-read, arXiv 2601.04463.) **This is the primary recall lever.**
- **B2 · Temperature-decorrelated multi-sampling** — sample the formation call
  twice per window (T=0 then T=0.7); union candidates by `(kind, normalized
  content)`, preferring the candidate that carries a supersession link on
  collision. Two T=0 samples are highly correlated and add nothing — the second
  sample MUST be T>0. Config-gated (`[memory_delta] decorrelated_samples`,
  default off). (Self-consistency, Wang et al. 2022.)

### Batch C — facet dual-granularity index + retrieval heads (schema + retrieval; `store/fts.py`, `retrieval/associative.py`, migration)

- **C1 · Facet index** — attach 2–6 atomic facets (proper nouns / dates /
  quantities / activity phrases) to each dense memory at formation time, stored
  in a separate `atom_facets` table. Facets are **addressing handles only, never
  surfaced as facts** — probes, reports, and answer context see the dense memory
  only. (MemGAS multi-granularity index, ICLR 2026 / arXiv 2505.19549.)
- **C2 · Facet head** — a retrieval pool that lexically matches facets and votes
  for the parent dense memory (coverage bonus), fused into the existing
  weighted-RRF bank. (MemGAS multi-granularity selection.)
- **C3 · Temporal-decay head** — lexical overlap × recency decay × confidence.
  (SYNAPSE time decay, arXiv 2601.02744.)
- **C4 · Association head (Hebbian)** — same-session co-formation counts as edge
  weight; seeds spread activation along edges, capped at 5 neighbors per seed
  (lateral inhibition). (HeLa-Mem arXiv 2604.16839 + SYNAPSE lateral inhibition.)

Each new head is label-blind, query-uniform, query-time read-only, per-head
vote telemetry, and enters the existing RRF fusion (`rrf_k=60`).

## 2. Excluded — DISCARDED by the lab's paired gate; do NOT port

- **MMR retrieval diversity** — answer models benefit from redundant confirmation
  of key facts; diversification induces hallucination (negative transfer,
  Skill2Mem). This fork already exposes `vector_recall_diversity_lambda` (default
  0.0 = off): keep it off; document it as known-ineffective and remove it if it
  costs nothing to do so. Do not enable it anywhere.
- **Surprise / state-transition gating** (Titans/MIRAS) — lab M2-R1 gate FAIL,
  rolled back.
- **Standalone dense head added on top** (M3-R1) — orthogonal noise, DISCARD.
- **Entropy-based dynamic head weights** — suppresses hesitant-but-correct heads.
- **Episode grouping (seed→sibling atoms)** — no gain under dense-memory form.

## 3. Eval protocol (persome-domain adaptation of the lab's discipline)

Persome cannot run HaluMem directly (screen sessions, not conversations), so the
gate is an offline golden fixture, built once and frozen:

- **Golden fixture**: `tests/fixtures/formation_golden/` — a hand-built persome
  session (timeline blocks) containing (i) N owner-authored durable facts with
  known gold memories, (ii) distractors an app/assistant merely displayed
  (must NOT be extracted), (iii) at least one considered-but-rejected option and
  one relative-time reference. Label-blind; frozen before any tuning.
- **Metrics** (mirror the lab's four): precision (no distractor/assistant fact
  admitted), recall (gold owner-facts admitted), calendar-resolution rate,
  polarity-correctness.
- **Gate discipline** (lab §3.2): a mechanism ships only if, on the frozen
  fixture, recall rises OR precision rises with the other not regressing beyond
  the measured noise floor; report per-mechanism deltas. Batch A/B run under
  `PERSOME_LLM_MOCK` for determinism where possible, plus one live pass on the
  fixture. No mechanism that fails its criterion ships silently — record it.
- Every existing gate still passes: `PERSOME_LLM_MOCK=1 uv run pytest -m "not
  macos and not integration"`, `ruff check`, `ruff format --check`,
  `secret_scan.py`, `pii_scan.py`, `language_scan.py`.

## 4. Engineering blueprint

```
Batch A  src/persome/prompts/memory_delta.md         # A1-A4 principles
         src/persome/writer/memory_delta.py          # authored-source gate, polarity on assertions, now-anchor
         src/persome/writer/delta_apply.py           # gate wiring if needed
Batch B  src/persome/writer/agent.py                 # pass-2 re-read call site (short cursor blocks only)
         src/persome/writer/memory_delta.py          # decorrelated dual-sample + union-dedup
         src/persome/config.py                        # [memory_delta] completeness_reread, decorrelated_samples
Batch C  src/persome/store/fts.py                     # atom_facets schema + _facet_pool + _temporal_pool + _association_pool
         src/persome/retrieval/associative.py         # register new heads into fusion
         src/persome/store/schema_dump.py             # regen committed schema
         src/persome/config.py                        # head weights (default neutral/off until fixture-validated)
Cleanup  src/persome/config.py + vector_recall.py     # MMR documented known-ineffective; keep default 0.0
Tests    tests/fixtures/formation_golden/, tests/test_formation_upgrade.py, tests/test_facet_retrieval.py
Docs     docs/memory-formation-upgrade.md (this), MEMORY_FORMAT.md / docs where behavior changes
```

Batch C changes SQLite schema → it must go through the same `store/fts.py`
single-owner EXCLUSIVE connection contract (commit d59cb47); regen the committed
schema (`scripts/regen_db_schema.py`) and pass `test_db_schema_drift`.

## 5. Acceptance criteria

- **AC-1**  `memory_delta.md` encodes A1-A4; the gate rejects a quote sourced
  from non-owner-authored text on the golden fixture.
- **AC-2**  Assertions/events on the fixture are dense self-contained sentences
  (no fragment atoms); a spot-check assertion contains ≥4 of who/what/when/where/
  how-much/why when the source provides them.
- **AC-3**  Every relative-time reference in the fixture resolves to an absolute
  date; calendar-resolution rate == 100% of resolvable references.
- **AC-4**  The considered-but-rejected option is stored with stance wording, not
  as fact; the assistant-proposed-unadopted option is absent. Polarity-correctness
  == 100% on the fixture.
- **AC-5**  Completeness re-read (B1) raises recall on the fixture vs Batch-A-only,
  with precision not regressing beyond the noise floor; config-gated, default off.
- **AC-6**  Decorrelated dual-sample (B2) second sample is T>0; union-dedup keeps
  supersession-linked candidates; config-gated, default off.
- **AC-7**  `atom_facets` table exists via the EXCLUSIVE-connection path; facets
  never appear in probe/report/answer output; schema-drift test passes.
- **AC-8**  Facet, temporal-decay, and association heads register into weighted
  RRF, are label-blind/read-only with per-head telemetry, and each earns its
  inclusion on the fixture or is left default-off with the negative result recorded.
- **AC-9**  MMR diversity remains default-off and is documented as known-ineffective
  per the lab ledger; nothing enables it.
- **AC-10** Full offline suite + ruff + secret/pii/language gates all pass; new
  fixture tests included; `git commit -s` per batch with a per-mechanism message
  citing its public anchor.
- **AC-11** Final report `docs/memory-formation-upgrade-report.md` tabulates each
  mechanism: shipped / default-off / rejected, with the fixture deltas and the
  public anchor — mirroring the lab ledger format.

## 6. Discipline

- One mechanism per commit where practical; every commit `-s` (DCO), message
  names the public anchor.
- No architecture regression: Batch C respects the single-owner EXCLUSIVE
  connection contract; retrieval heads stay read-only.
- Batches land A → B → C; the golden fixture is frozen before Batch A tuning and
  never edited to make a mechanism pass.
- Silence is not success: a mechanism that fails its fixture criterion is recorded
  in the report as rejected/default-off, not quietly dropped.
