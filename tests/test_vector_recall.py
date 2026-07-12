"""Local hashed n-gram vector recall: fusion, defaults, and fail-open."""

from __future__ import annotations

from types import SimpleNamespace

from persome.evomem import vector_recall
from persome.evomem.engine import EvoMemory
from persome.evomem.models import MemoryLayer


def _cfg(enabled: bool) -> SimpleNamespace:
    return SimpleNamespace(evomem=SimpleNamespace(vector_recall_enabled=enabled))


def _node(node_id: str, content: str) -> SimpleNamespace:
    return SimpleNamespace(node_id=node_id, content=content)


def test_embed_similarity_orders_related_before_unrelated() -> None:
    coffee = "\u559c\u6b22\u559d\u5496\u5561"  # likes drinking coffee
    coffee_query = "\u5496\u5561\u7231\u597d"  # coffee preference
    unrelated = "\u4eca\u5929\u5f00\u4f1a\u5f88\u665a"  # unrelated meeting note
    query_vec = vector_recall.embed(coffee_query)
    assert vector_recall.cosine(query_vec, vector_recall.embed(coffee)) > vector_recall.cosine(
        query_vec, vector_recall.embed(unrelated)
    )
    assert vector_recall.embed("") == {}


def test_fuse_disabled_returns_lexical_hits_unchanged() -> None:
    lexical = [{"node_id": "a", "score": 1.0, "node": _node("a", "text")}]
    out = vector_recall.fuse(
        "query",
        lexical,
        top_k=5,
        candidates_provider=lambda: [_node("b", "query text")],
        cfg=_cfg(False),
    )
    assert out is lexical


def test_fuse_surfaces_vector_only_hits_when_enabled() -> None:
    coffee = _node("n-coffee", "\u559c\u6b22\u559d\u5496\u5561")
    other = _node("n-other", "completely different topic")
    out = vector_recall.fuse(
        "\u5496\u5561\u7231\u597d",
        [],
        top_k=5,
        candidates_provider=lambda: [other, coffee],
        cfg=_cfg(True),
    )
    assert [hit["node_id"] for hit in out] == ["n-coffee"]


def test_fuse_merges_lexical_and_vector_rankings() -> None:
    shared = _node("n-shared", "espresso ritual every morning")
    vector_only = _node("n-vector", "morning espresso before standup")
    lexical = [{"node_id": "n-shared", "score": 1.0, "node": shared}]
    out = vector_recall.fuse(
        "morning espresso",
        lexical,
        top_k=5,
        candidates_provider=lambda: [shared, vector_only],
        cfg=_cfg(True),
    )
    ids = [hit["node_id"] for hit in out]
    assert set(ids) == {"n-shared", "n-vector"}
    # The node ranked by both paths outscores the vector-only node.
    assert ids[0] == "n-shared"


def test_fuse_fails_open_on_broken_candidates() -> None:
    def broken() -> list:
        raise RuntimeError("store unavailable")

    lexical = [{"node_id": "a", "score": 1.0, "node": _node("a", "text")}]
    assert (
        vector_recall.fuse("q", lexical, top_k=5, candidates_provider=broken, cfg=_cfg(True))
        is lexical
    )


def test_engine_search_default_stays_lexical_only(ac_root) -> None:
    mem = EvoMemory()
    mem.add_direct("prefers oat milk in coffee", layer=MemoryLayer.L2_FACT)
    hits = mem.search("oat milk")
    assert [h["node"].content for h in hits] == ["prefers oat milk in coffee"]


def test_engine_search_fuses_when_enabled(ac_root, monkeypatch) -> None:
    from persome import config as config_mod

    mem = EvoMemory()
    coffee = "\u6bcf\u5929\u65e9\u4e0a\u559d\u5496\u5561"  # drinks coffee every morning
    mem.add_direct(coffee, layer=MemoryLayer.L2_FACT)
    real_load = config_mod.load

    def patched_load(*args, **kwargs):
        cfg = real_load(*args, **kwargs)
        cfg.evomem.vector_recall_enabled = True
        return cfg

    monkeypatch.setattr(config_mod, "load", patched_load)
    # No full token overlap needed: the CJK bigram for "coffee" carries the hit.
    hits = mem.search("\u5496\u5561\u7231\u597d")
    assert coffee in [h["node"].content for h in hits]
