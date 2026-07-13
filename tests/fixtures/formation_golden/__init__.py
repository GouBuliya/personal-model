"""Frozen golden fixture for the formation-upgrade gate (spec §3).

A hand-built persome screen session (timeline blocks) with known gold
owner-authored facts, distractors that only appear in displayed/received text,
one considered-but-rejected option, and one relative-time reference. FROZEN:
do not edit to make a mechanism pass — that is the "don't mistake luck for
signal" discipline ported from the owner's research lab (agent-memory-lab
SPEC §3.2).

Authored spans use the parser's ``<message dir="sent" …>`` markup (the
deterministic owner-authored signal, parsers/base.py ``_DIRECTION_ATTR``) and a
terminal ``typed:`` line; distractors use ``dir="received"`` / ``<preview>`` /
plain displayed entries. The session date anchor is 2026-07-13.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from persome.timeline.store import TimelineBlock

SESSION_DATE = datetime(2026, 7, 13, 15, 0, tzinfo=None)
SESSION_DATE_ISO = "2026-07-13"


@dataclass(frozen=True)
class GoldItem:
    """One expected outcome the gated delta must (or must not) contain."""

    kind: str  # assertion | relation | event | entity
    must_contain: tuple[str, ...]  # substrings the dense memory must carry
    present: bool = True  # True = must be extracted; False = distractor, must be absent
    polarity: str | None = None  # expected polarity when applicable ("+"/"-"/"0")
    calendar: str | None = None  # absolute date the item must resolve a relative time to
    note: str = ""


def _block(
    start: str,
    end: str,
    apps: list[str],
    entries: list[str],
    focus_structured: str = "",
) -> TimelineBlock:
    return TimelineBlock(
        start_time=datetime.fromisoformat(f"2026-07-13T{start}:00"),
        end_time=datetime.fromisoformat(f"2026-07-13T{end}:00"),
        entries=entries,
        apps_used=apps,
        focus_structured=focus_structured,
    )


def golden_blocks() -> list[TimelineBlock]:
    """The frozen session as the timeline stage would produce it."""
    return [
        # ── Block 1: WeChat conversation with \u5f20\u4f1f ──────────────────────────
        _block(
            "14:30",
            "14:40",
            ["WeChat"],
            [
                "[WeChat] Conversation with \u5f20\u4f1f: the owner confirmed a decision "
                "and declined an alternative; \u5f20\u4f1f shared their own plan.",
            ],
            focus_structured=(
                '<screen_conversation app="WeChat">\n'
                '<message dir="received" sender="\u5f20\u4f1f" time="14:31">'
                "\u6211\u4e0b\u5468\u4e00\u5165\u804c\u817e\u8baf\u6df7\u5143\u505a\u5927\u6a21\u578b\u5bf9\u9f50</message>\n"
                '<message dir="sent" sender="self" time="14:33">'
                "\u6211\u51b3\u5b9a\u8fd9\u4e2a\u5b63\u5ea6\u5168\u804c\u505a memory-lab \u7684\u8bb0\u5fc6\u5206\u652f\u8bad\u7ec3\uff0c"
                "\u5148\u5728 A10 \u4e0a\u8dd1 v0 \u57fa\u7ebf</message>\n"
                '<message dir="sent" sender="self" time="14:35">'
                "\u6211\u672c\u6765\u60f3\u7528 enwik8 \u5f53\u8bad\u7ec3\u8bed\u6599\uff0c\u540e\u6765\u56e0\u4e3a\u4e0b\u8f7d\u6e90\u88ab\u5899\u6539\u7528\u4e86 "
                "wikitext-103</message>\n"
                '<message dir="received" sender="\u5f20\u4f1f" time="14:36">'
                "\u8981\u4e0d\u8981\u8bd5\u8bd5 Titans \u90a3\u5957 surprise gating</message>\n"
                '<message dir="sent" sender="self" time="14:37">'
                "\u660e\u5929\u4e0b\u5348\u4e09\u70b9\u6211\u4eec\u5f00\u4e2a\u4f1a\u5bf9\u9f50 ICML 2026 \u57fa\u51c6\u7684\u8bc4\u6d4b\u534f\u8bae</message>\n"
                "</screen_conversation>"
            ),
        ),
        # ── Block 2: terminal — owner types a command / decision ────────────
        _block(
            "15:05",
            "15:12",
            ["cmux"],
            [
                "[cmux] Agent memory training: the owner typed a goal setting the "
                "training route; the assistant proposed an option in its output.",
            ],
            focus_structured=(
                "<terminal>\n"
                "typed: \u8def\u7ebf\u5b9a\u6b7b v0 \u53ef\u6d4b\u6548\u679c\u540e\u6267\u884c v1 \u8bb0\u5fc6\u8bfe\u7a0b\uff0c"
                "\u6700\u540e\u7528 ICML 2026 \u57fa\u51c6\u4e09\u65b9\u5bf9\u6bd4\n"
                "assistant_output: \u5efa\u8bae\u6539\u7528 MMR \u591a\u6837\u6027\u5316\u68c0\u7d22\u7ed3\u679c\u6765\u63d0\u5347\u8986\u76d6\n"
                "</terminal>"
            ),
        ),
    ]


def gold_items() -> list[GoldItem]:
    """Expected gate outcomes on the frozen session."""
    return [
        # PRESENT — owner-authored durable facts (dir="sent" / typed) --------
        GoldItem(
            kind="assertion",
            must_contain=("memory-lab", "\u8bb0\u5fc6\u5206\u652f", "A10"),
            present=True,
            note="dense self-contained: what + where the owner committed to this quarter",
        ),
        GoldItem(
            kind="assertion",
            must_contain=("wikitext-103",),
            present=True,
            polarity="+",
            note="final state after a revision (enwik8 → wikitext-103); only final state",
        ),
        GoldItem(
            kind="event",
            must_contain=(SESSION_DATE_ISO, "2026-07-14"),
            present=True,
            calendar="2026-07-14",
            note="'\u660e\u5929\u4e0b\u5348\u4e09\u70b9' on 2026-07-13 must resolve to 2026-07-14 15:00",
        ),
        # PRESENT — considered-but-rejected, stored WITH stance wording ------
        GoldItem(
            kind="assertion",
            must_contain=("enwik8",),
            present=True,
            polarity="-",
            note="owner 'considered enwik8 but switched' — stance, never a bare fact",
        ),
        # ABSENT — distractors ------------------------------------------------
        GoldItem(
            kind="assertion",
            must_contain=("Titans", "surprise"),
            present=False,
            note="\u5f20\u4f1f floated it as a question (dir=received suggestion); the owner did "
            "not adopt it and nothing happened — tense/adoption discipline excludes it",
        ),
        GoldItem(
            kind="assertion",
            must_contain=("MMR", "\u591a\u6837\u6027"),
            present=False,
            note="assistant_output proposed it — assistant/system output can NEVER be "
            "evidence (spec A1); the deterministic gate strips these spans",
        ),
    ]


# Authored-span markers the deterministic gate keys on (spec A1). A quote grounds
# an owner-stance item only when it lies inside one of these.
AUTHORED_MARKERS: tuple[str, ...] = ('dir="sent"', "typed:")
DISPLAYED_MARKERS: tuple[str, ...] = ('dir="received"', "<preview", "assistant_output:")


@dataclass(frozen=True)
class FixtureScore:
    precision: float
    recall: float
    calendar_rate: float
    polarity_rate: float
    detail: dict = field(default_factory=dict)
