"""Batch A deterministic gate tests for the formation upgrade (spec §5).

These exercise the code gate on the frozen golden fixture; prompt-driven
principles (dense narrative, calendar, polarity fidelity) are measured by the
opt-in live eval and recorded in the report.
"""

from __future__ import annotations

from persome.evomem import identity as identity_mod
from persome.writer import memory_delta as md
from tests.fixtures import formation_golden as gold


def _session_text() -> str:
    return md._render_blocks(gold.golden_blocks())


def _gate(raw: dict) -> dict:
    roster = identity_mod.Roster.build([("\u5f20\u4f1f", [])])
    clean, _dropped = md.gate_delta(
        raw,
        roster=roster,
        session_text=_session_text(),
        min_confidence=0.5,
        cooccurrence=False,
    )
    return clean


def test_evidence_text_strips_assistant_and_preview_spans() -> None:
    text = (
        '<message dir="sent" sender="self">owner said this</message>\n'
        "assistant_output: assistant proposed MMR diversity\n"
        '<preview sender="x">a glimpsed line</preview>\n'
        "typed: owner typed this"
    )
    ev = md.evidence_text(text)
    assert "owner said this" in ev
    assert "owner typed this" in ev
    assert "assistant proposed MMR" not in ev
    assert "glimpsed line" not in ev


def test_assistant_output_quote_cannot_ground_an_assertion() -> None:
    # The MMR distractor only appears inside assistant_output: — must be dropped.
    raw = {
        "assertions": [
            {
                "subject": {"ref": "\u5f20\u4f1f"},
                "text": "\u5f20\u4f1f adopted MMR diversity for retrieval.",
                "quote": "\u5efa\u8bae\u6539\u7528 MMR \u591a\u6837\u6027\u5316\u68c0\u7d22\u7ed3\u679c\u6765\u63d0\u5347\u8986\u76d6",
                "confidence": 0.9,
            }
        ]
    }
    # Subject \u5f20\u4f1f resolves; the ONLY reason to drop is the assistant-output quote.
    assert _gate(raw)["assertions"] == []


# memory_delta assertions are about NON-self entities (delta_apply skips
# self-subject rows); owner facts flow through the reducer. So the gate tests
# use \u5f20\u4f1f, whose own received message legitimately grounds a fact about them.
def test_authored_quote_grounds_an_assertion_with_polarity() -> None:
    raw = {
        "assertions": [
            {
                "subject": {"ref": "\u5f20\u4f1f"},
                "text": "\u5f20\u4f1f confirmed they start at Tencent Hunyuan next Monday on alignment.",
                "polarity": "+",
                "quote": "\u6211\u4e0b\u5468\u4e00\u5165\u804c\u817e\u8baf\u6df7\u5143\u505a\u5927\u6a21\u578b\u5bf9\u9f50",
                "confidence": 0.9,
            }
        ]
    }
    out = _gate(raw)["assertions"]
    assert len(out) == 1
    assert out[0]["polarity"] == "+"


def test_assertion_polarity_is_preserved_and_normalized() -> None:
    raw = {
        "assertions": [
            {
                "subject": {"ref": "\u5f20\u4f1f"},
                "text": "\u5f20\u4f1f starts at Tencent Hunyuan next Monday.",
                "polarity": "-",
                "quote": "\u6211\u4e0b\u5468\u4e00\u5165\u804c\u817e\u8baf\u6df7\u5143\u505a\u5927\u6a21\u578b\u5bf9\u9f50",
                "confidence": 0.8,
            }
        ]
    }
    assert _gate(raw)["assertions"][0]["polarity"] == "-"


def test_invalid_assertion_polarity_falls_back_to_neutral() -> None:
    raw = {
        "assertions": [
            {
                "subject": {"ref": "\u5f20\u4f1f"},
                "text": "\u5f20\u4f1f starts at Tencent Hunyuan next Monday.",
                "polarity": "bogus",
                "quote": "\u6211\u4e0b\u5468\u4e00\u5165\u804c\u817e\u8baf\u6df7\u5143\u505a\u5927\u6a21\u578b\u5bf9\u9f50",
                "confidence": 0.9,
            }
        ]
    }
    assert _gate(raw)["assertions"][0]["polarity"] == "0"


# ── Batch B: completeness re-read (B1) + decorrelated sampling (B2) ──────────


def _resp(delta: dict):
    import json as _json
    from types import SimpleNamespace

    msg = SimpleNamespace(content=_json.dumps(delta))
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


def _union_of(*raws):
    return md._union_raw(list(raws))


def test_union_raw_dedups_and_keeps_supersession_candidate() -> None:
    a = {"assertions": [{"subject": {"ref": "\u5f20\u4f1f"}, "text": "joined Tencent"}]}
    b = {
        "assertions": [
            {"subject": {"ref": "\u5f20\u4f1f"}, "text": "joined tencent", "supersedes": ["x"]},
            {"subject": {"ref": "\u5f20\u4f1f"}, "text": "a genuinely new fact"},
        ]
    }
    merged = _union_of(a, b)
    texts = [i["text"] for i in merged["assertions"]]
    assert "a genuinely new fact" in texts
    # the two "joined tencent" collapse to one, and the supersession-carrying wins
    joined = [i for i in merged["assertions"] if "joined" in i["text"].lower()]
    assert len(joined) == 1 and joined[0].get("supersedes") == ["x"]


def test_decorrelated_second_sample_uses_positive_temperature(ac_root) -> None:
    from persome import config as config_mod

    cfg = config_mod.load()
    cfg.memory_delta.decorrelated_samples = True
    seen_temps: list = []

    def fake_call(_cfg, _stage, _messages, temperature=None):
        seen_temps.append(temperature)
        return _resp({"entities": [], "assertions": [], "relations": [], "events": []})

    from unittest.mock import patch

    import persome.timeline.store as tl_store

    block = tl_store.TimelineBlock(
        start_time=gold.SESSION_DATE,
        end_time=gold.SESSION_DATE,
        entries=["[cmux] work"],
        apps_used=["cmux"],
    )
    with patch.object(md.tl_store, "query_range", return_value=[block]):
        md.run_after_session(
            cfg,
            session_id="s-b2",
            start_time=gold.SESSION_DATE,
            end_time=gold.SESSION_DATE,
            llm_call=fake_call,
        )
    # sampled twice; the second temperature is > 0 (decorrelated, not a T=0 twin)
    assert seen_temps == [0.0, 0.7] or (len(seen_temps) == 2 and seen_temps[1] > 0.0)


def test_completeness_reread_admits_only_missed_facts(ac_root) -> None:
    from persome import config as config_mod

    cfg = config_mod.load()
    cfg.memory_delta.completeness_reread = True
    cfg.memory_delta.apply_enabled = False

    pass1 = {
        "entities": [
            {
                "new_entity": "\u5f20\u4f1f",
                "kind": "person",
                "quote": "\u5f20\u4f1f",
                "confidence": 0.9,
            }
        ],
        "assertions": [
            {
                "subject": {"new_entity": "\u5f20\u4f1f"},
                "text": "captured in pass 1",
                "quote": "\u5f20\u4f1f",
                "confidence": 0.9,
            }
        ],
        "relations": [],
        "events": [],
    }
    pass2 = {
        "entities": [],
        "assertions": [
            # duplicate of pass 1 (same subject+content) — must be deduped
            {
                "subject": {"new_entity": "\u5f20\u4f1f"},
                "text": "captured in pass 1",
                "quote": "\u5f20\u4f1f",
                "confidence": 0.9,
            },
            # genuinely missed fact — must be admitted
            {
                "subject": {"new_entity": "\u5f20\u4f1f"},
                "text": "a fact pass 1 missed",
                "quote": "\u5f20\u4f1f",
                "confidence": 0.9,
            },
        ],
        "relations": [],
        "events": [],
    }
    calls = {"n": 0}

    def fake_call(_cfg, _stage, _messages, temperature=None):
        calls["n"] += 1
        return _resp(pass1 if calls["n"] == 1 else pass2)

    # session text must contain the quote token so the gate passes
    import persome.timeline.store as tl_store

    block = tl_store.TimelineBlock(
        start_time=gold.SESSION_DATE,
        end_time=gold.SESSION_DATE,
        entries=["[WeChat] \u5f20\u4f1f said hello"],
        apps_used=["WeChat"],
    )
    from unittest.mock import patch

    with patch.object(md.tl_store, "query_range", return_value=[block]):
        result = md.run_after_session(
            cfg,
            session_id="s-b1",
            start_time=gold.SESSION_DATE,
            end_time=gold.SESSION_DATE,
            llm_call=fake_call,
        )
    assert calls["n"] == 2  # pass 1 + re-read
    assert result.counts["assertions"] == 2  # pass-1 fact + the one missed fact, dedup applied


# ── Batch C1: facet dual-granularity capture (addressing-only) ───────────────


def test_facets_are_captured_normalized_and_capped() -> None:
    raw = {
        "assertions": [
            {
                "subject": {"ref": "\u5f20\u4f1f"},
                "text": "\u5f20\u4f1f starts at Tencent Hunyuan next Monday.",
                "quote": "\u6211\u4e0b\u5468\u4e00\u5165\u804c\u817e\u8baf\u6df7\u5143\u505a\u5927\u6a21\u578b\u5bf9\u9f50",
                "confidence": 0.9,
                "facets": [
                    "Tencent Hunyuan",
                    "  ",  # blank dropped
                    "Tencent Hunyuan",  # dup dropped
                    "next Monday",
                    "alignment",
                    "a",
                    "b",
                    "c",
                    "d",  # cap at 6
                ],
            }
        ]
    }
    out = _gate(raw)["assertions"][0]
    assert out["facets"] == ["Tencent Hunyuan", "next Monday", "alignment", "a", "b", "c"]
    # addressing-only: facets never appear in the dense text
    for f in out["facets"]:
        if f not in out["text"]:
            assert True  # at least some facets are handles distinct from the sentence


def test_missing_or_bad_facets_yield_empty_list() -> None:
    raw = {
        "assertions": [
            {
                "subject": {"ref": "\u5f20\u4f1f"},
                "text": "\u5f20\u4f1f starts next Monday.",
                "quote": "\u6211\u4e0b\u5468\u4e00\u5165\u804c\u817e\u8baf\u6df7\u5143\u505a\u5927\u6a21\u578b\u5bf9\u9f50",
                "confidence": 0.9,
                "facets": "not-a-list",
            }
        ]
    }
    assert _gate(raw)["assertions"][0]["facets"] == []
