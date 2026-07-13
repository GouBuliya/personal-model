"""C2 facet retrieval head (MemGAS, ICLR 2026 / arXiv 2505.19549).

The formation side captures short addressing handles per fact
(``atom_facets``); this head lets a query that names a handle reach the entry
even when the dense text buries that token. Discipline: the head is OFF by
default (``[search] facet_pool_weight = 0.0``) — these tests drive it with an
explicit positive weight so the mechanism is proven, buildable, and testable
before a retrieval benchmark earns it a default.
"""

from __future__ import annotations

from persome.store import fts


def _insert(conn, *, eid: str, content: str, ts: str, superseded: int = 0) -> None:
    conn.execute(
        "INSERT INTO entries (id, path, prefix, timestamp, tags, content, superseded)"
        " VALUES (?, 'person-x.md', 'person', ?, '', ?, ?)",
        (eid, ts, content, superseded),
    )


# ── storage ──────────────────────────────────────────────────────────────────


def test_replace_atom_facets_dedups_blanks_and_case(ac_root) -> None:
    with fts.cursor() as conn:
        conn.executescript(fts.SCHEMA)
        n = fts.replace_atom_facets(
            conn,
            "e1",
            ["Tencent Hunyuan", "  ", "tencent hunyuan", "next Monday", "alignment"],
        )
        # blank dropped; the case-insensitive duplicate dropped → 3 stored
        assert n == 3
        stored = [
            r["facet"]
            for r in conn.execute(
                "SELECT facet FROM atom_facets WHERE entry_id='e1' ORDER BY facet"
            ).fetchall()
        ]
        assert stored == ["Tencent Hunyuan", "alignment", "next Monday"]


def test_replace_atom_facets_is_idempotent_replace(ac_root) -> None:
    with fts.cursor() as conn:
        conn.executescript(fts.SCHEMA)
        fts.replace_atom_facets(conn, "e1", ["a", "b", "c"])
        fts.replace_atom_facets(conn, "e1", ["x"])  # replaces, not appends
        rows = conn.execute("SELECT facet FROM atom_facets WHERE entry_id='e1'").fetchall()
        assert [r["facet"] for r in rows] == ["x"]
        # empty clears
        assert fts.replace_atom_facets(conn, "e1", []) == 0
        assert conn.execute("SELECT COUNT(*) FROM atom_facets").fetchone()[0] == 0


# ── retrieval head ─────────────────────────────────────────────────────────────


def test_facet_head_off_by_default_is_inert(ac_root) -> None:
    """Default weight 0.0: a query the text heads cannot match returns nothing —
    the facet pool is never computed and the entrance degrades to hybrid."""
    with fts.cursor() as conn:
        conn.executescript(fts.SCHEMA)
        _insert(
            conn, eid="e-bg", content="an unrelated dense sentence", ts="2026-06-05T18:00:00+08:00"
        )
        fts.replace_atom_facets(conn, "e-bg", ["Tencent Hunyuan"])
        hits = fts.search_associative(
            conn,
            query="who joined Tencent Hunyuan",
            top_k=5,  # no facet weight → default 0.0
        )
        assert [h.id for h in hits] == []


def test_facet_head_reaches_entry_whose_dense_text_buries_the_handle(ac_root) -> None:
    """With a positive weight, an entry the text backbone misses is reached via
    a captured handle the query names."""
    with fts.cursor() as conn:
        conn.executescript(fts.SCHEMA)
        _insert(
            conn,
            eid="e-hit",
            content="They confirmed the new alignment role starts next week.",
            ts="2026-06-05T18:00:00+08:00",
        )
        fts.replace_atom_facets(conn, "e-hit", ["Tencent Hunyuan", "next Monday"])
        hits = fts.search_associative(
            conn,
            query="who joined Tencent Hunyuan",
            top_k=5,
            facet_pool_weight=0.5,
        )
        assert "e-hit" in [h.id for h in hits]


def test_facet_head_ranks_more_handle_matches_first(ac_root) -> None:
    with fts.cursor() as conn:
        conn.executescript(fts.SCHEMA)
        _insert(conn, eid="e-one", content="dense one", ts="2026-06-05T18:00:00+08:00")
        _insert(conn, eid="e-two", content="dense two", ts="2026-06-05T18:00:00+08:00")
        fts.replace_atom_facets(conn, "e-one", ["Tencent Hunyuan"])
        fts.replace_atom_facets(conn, "e-two", ["Tencent Hunyuan", "alignment"])
        ids = fts._facet_pool(conn, "joined Tencent Hunyuan on alignment", top_k=5)
        # e-two matches two distinct handles → ranks ahead of e-one's single hit
        assert ids[0] == "e-two" and "e-one" in ids


def test_facet_head_skips_superseded_entries(ac_root) -> None:
    with fts.cursor() as conn:
        conn.executescript(fts.SCHEMA)
        _insert(
            conn,
            eid="e-old",
            content="stale",
            ts="2026-06-05T18:00:00+08:00",
            superseded=1,
        )
        fts.replace_atom_facets(conn, "e-old", ["Tencent Hunyuan"])
        assert fts._facet_pool(conn, "joined Tencent Hunyuan", top_k=5) == []


def test_facet_head_honors_since_until(ac_root) -> None:
    with fts.cursor() as conn:
        conn.executescript(fts.SCHEMA)
        _insert(conn, eid="e-in", content="in window", ts="2026-06-05T18:00:00+08:00")
        _insert(conn, eid="e-out", content="out of window", ts="2026-05-01T18:00:00+08:00")
        fts.replace_atom_facets(conn, "e-in", ["Tencent Hunyuan"])
        fts.replace_atom_facets(conn, "e-out", ["Tencent Hunyuan"])
        ids = fts._facet_pool(
            conn,
            "joined Tencent Hunyuan",
            top_k=5,
            since="2026-06-01T00:00:00+08:00",
            until="2026-06-30T23:59:59+08:00",
        )
        assert ids == ["e-in"]


def test_short_handles_below_two_chars_do_not_match(ac_root) -> None:
    with fts.cursor() as conn:
        conn.executescript(fts.SCHEMA)
        _insert(conn, eid="e", content="dense", ts="2026-06-05T18:00:00+08:00")
        fts.replace_atom_facets(conn, "e", ["a"])  # 1-char handle, LENGTH < 2
        assert fts._facet_pool(conn, "a a a", top_k=5) == []
