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
