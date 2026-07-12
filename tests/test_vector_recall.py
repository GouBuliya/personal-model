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


def _dense_cfg(**overrides):
    base = {
        "vector_recall_enabled": True,
        "vector_recall_backend": "ollama",
        "vector_recall_model": "fake-embed",
        "vector_recall_dimension": 3,
    }
    base.update(overrides)
    return SimpleNamespace(evomem=SimpleNamespace(**base))


class _FakeEmbedder:
    """Deterministic stand-in for OllamaEmbedder with call accounting."""

    model = "fake-embed"

    def __init__(self) -> None:
        self.batch_calls: list[list[str]] = []

    def _vector(self, text: str) -> list[float]:
        if "coffee" in text:
            return [1.0, 0.0, 0.0]
        if "tea" in text:
            return [0.0, 1.0, 0.0]
        return [0.0, 0.0, 1.0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        self.batch_calls.append(list(texts))
        return [self._vector(t) for t in texts]

    def embed(self, text: str) -> list[float]:
        return self._vector(text)


def test_ollama_contract_validation_rejects_bad_payloads() -> None:
    import pytest

    embedder = vector_recall.OllamaEmbedder(expected_dimension=3)
    good = {"embeddings": [[1.0, 0.0, 0.0]]}
    assert embedder._vectors(good, expected_count=1) == [[1.0, 0.0, 0.0]]
    with pytest.raises(vector_recall.EmbeddingContractError):
        embedder._vectors({"embeddings": [[1.0, 0.0]]}, expected_count=1)
    with pytest.raises(vector_recall.EmbeddingContractError):
        embedder._vectors({"embeddings": []}, expected_count=1)
    with pytest.raises(vector_recall.EmbeddingContractError):
        embedder._vectors({"embeddings": [[1.0, "x", 0.0]]}, expected_count=1)


def test_dense_backend_ranks_by_embedding_similarity(monkeypatch) -> None:
    fake = _FakeEmbedder()
    monkeypatch.setattr(vector_recall, "_make_embedder", lambda _evomem: fake)
    vector_recall._EMBED_CACHE.clear()
    coffee = _node("n-coffee", "morning coffee ritual")
    tea = _node("n-tea", "afternoon tea break")
    out = vector_recall.fuse(
        "fresh coffee brew",
        [],
        top_k=1,
        candidates_provider=lambda: [tea, coffee],
        cfg=_dense_cfg(),
    )
    assert [hit["node_id"] for hit in out] == ["n-coffee"]


def test_dense_backend_caches_unchanged_candidates(monkeypatch) -> None:
    fake = _FakeEmbedder()
    monkeypatch.setattr(vector_recall, "_make_embedder", lambda _evomem: fake)
    vector_recall._EMBED_CACHE.clear()
    nodes = [_node("n-coffee", "morning coffee ritual"), _node("n-tea", "afternoon tea break")]
    for _ in range(2):
        vector_recall.fuse(
            "fresh coffee brew",
            [],
            top_k=2,
            candidates_provider=lambda: nodes,
            cfg=_dense_cfg(),
        )
    # Candidate embeddings were batched exactly once; the second query reused the cache.
    assert len(fake.batch_calls) == 1
    assert sorted(fake.batch_calls[0]) == ["afternoon tea break", "morning coffee ritual"]


def test_dense_backend_fails_open_when_service_unreachable() -> None:
    vector_recall._EMBED_CACHE.clear()
    lexical = [{"node_id": "a", "score": 1.0, "node": _node("a", "text")}]
    out = vector_recall.fuse(
        "query",
        lexical,
        top_k=5,
        candidates_provider=lambda: [_node("b", "coffee")],
        cfg=_dense_cfg(vector_recall_ollama_url="http://127.0.0.1:1"),
    )
    assert out is lexical


def _cfg_full(**overrides):
    base = {"vector_recall_enabled": True}
    base.update(overrides)
    return SimpleNamespace(evomem=SimpleNamespace(**base))


def test_weighted_rrf_head_weights_flip_the_ranking() -> None:
    lex_node = _node("n-lex", "afternoon tea break")
    vec_node = _node("n-coffee", "\u559c\u6b22\u559d\u5496\u5561")
    lexical = [{"node_id": "n-lex", "score": 1.0, "node": lex_node}]
    provider = lambda: [lex_node, vec_node]  # noqa: E731

    favor_lexical = vector_recall.fuse(
        "\u5496\u5561\u7231\u597d",
        lexical,
        top_k=2,
        candidates_provider=provider,
        cfg=_cfg_full(vector_recall_lexical_weight=3.0, vector_recall_vector_weight=1.0),
    )
    assert favor_lexical[0]["node_id"] == "n-lex"

    favor_vector = vector_recall.fuse(
        "\u5496\u5561\u7231\u597d",
        lexical,
        top_k=2,
        candidates_provider=provider,
        cfg=_cfg_full(vector_recall_lexical_weight=1.0, vector_recall_vector_weight=3.0),
    )
    assert favor_vector[0]["node_id"] == "n-coffee"


def test_invalid_weights_fall_back_to_neutral() -> None:
    assert vector_recall._clean_weight("nan") == 1.0
    assert vector_recall._clean_weight(-2.0) == 1.0
    assert vector_recall._clean_weight(None) == 1.0
    assert vector_recall._clean_weight(2.5) == 2.5
    assert (
        vector_recall._diversity_lambda(SimpleNamespace(vector_recall_diversity_lambda=1.5)) == 0.0
    )
    assert (
        vector_recall._diversity_lambda(SimpleNamespace(vector_recall_diversity_lambda=0.3)) == 0.3
    )


def test_mmr_prefers_a_diverse_second_pick() -> None:
    dup_a = {"node_id": "a", "score": 1.0, "node": _node("a", "morning espresso ritual daily")}
    dup_b = {"node_id": "b", "score": 0.95, "node": _node("b", "daily morning espresso ritual")}
    diverse = {"node_id": "c", "score": 0.9, "node": _node("c", "runs along the river at dawn")}
    ranked = [dup_a, dup_b, diverse]
    plain = vector_recall._mmr_select(ranked, top_k=2, diversity_lambda=0.0)
    assert [h["node_id"] for h in plain] == ["a", "b"]
    mmr = vector_recall._mmr_select(ranked, top_k=2, diversity_lambda=0.6)
    assert [h["node_id"] for h in mmr] == ["a", "c"]


def test_expand_query_disabled_returns_raw() -> None:
    assert vector_recall.expand_query("who is alice", cfg=_cfg_full()) == "who is alice"
    off = SimpleNamespace(evomem=SimpleNamespace(vector_recall_enabled=False))
    assert vector_recall.expand_query("who is alice", cfg=off) == "who is alice"


def test_expand_query_prepends_views_and_caches(monkeypatch) -> None:
    from persome.writer import llm as llm_mod

    calls: list[str] = []

    def fake_call(cfg, stage, *, messages, **kwargs):
        calls.append(stage)
        content = "USER met Alice in Berlin.\nalice berlin conference"
        message = SimpleNamespace(content=content)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    monkeypatch.setattr(llm_mod, "call_llm", fake_call)
    vector_recall._REWRITE_CACHE.clear()
    cfg = _cfg_full(vector_recall_query_rewrite=True)
    expanded = vector_recall.expand_query("where did I meet alice?", cfg=cfg)
    assert expanded == (
        "USER met Alice in Berlin.\nalice berlin conference\nwhere did I meet alice?"
    )
    # Second call is served from the rewrite cache.
    vector_recall.expand_query("where did I meet alice?", cfg=cfg)
    assert calls == ["vector_recall_rewrite"]


def test_expand_query_fails_open_on_llm_error(monkeypatch) -> None:
    from persome.writer import llm as llm_mod

    def broken(cfg, stage, *, messages, **kwargs):
        raise RuntimeError("no credential")

    monkeypatch.setattr(llm_mod, "call_llm", broken)
    vector_recall._REWRITE_CACHE.clear()
    cfg = _cfg_full(vector_recall_query_rewrite=True)
    assert vector_recall.expand_query("where did I meet alice?", cfg=cfg) == (
        "where did I meet alice?"
    )


def test_mmr_overselects_the_vector_pool_so_diversity_has_material(monkeypatch) -> None:
    fake = _FakeEmbedder()
    monkeypatch.setattr(vector_recall, "_make_embedder", lambda _evomem: fake)
    vector_recall._EMBED_CACHE.clear()
    candidates = [
        _node("n-coffee-1", "morning coffee ritual daily"),
        _node("n-coffee-2", "daily morning coffee ritual"),
        _node("n-tea", "afternoon tea break"),
    ]
    plain = vector_recall.fuse(
        "coffee",
        [],
        top_k=2,
        candidates_provider=lambda: candidates,
        cfg=_dense_cfg(vector_recall_diversity_lambda=0.0),
    )
    assert [h["node_id"] for h in plain] == ["n-coffee-1", "n-coffee-2"]
    vector_recall._EMBED_CACHE.clear()
    diverse = vector_recall.fuse(
        "coffee",
        [],
        top_k=2,
        candidates_provider=lambda: candidates,
        cfg=_dense_cfg(vector_recall_diversity_lambda=0.6),
    )
    # Without pool over-selection the tea memory would never reach MMR.
    assert [h["node_id"] for h in diverse] == ["n-coffee-1", "n-tea"]


def test_openai_compatible_contract_validation() -> None:
    import pytest

    embedder = vector_recall.OpenAICompatibleEmbedder(expected_dimension=3)
    good = {
        "data": [
            {"index": 1, "embedding": [0.0, 1.0, 0.0]},
            {"index": 0, "embedding": [1.0, 0.0, 0.0]},
        ]
    }
    # Rows are re-ordered by index before validation.
    assert embedder._vectors(good, expected_count=2) == [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
    with pytest.raises(vector_recall.EmbeddingContractError):
        embedder._vectors({"data": [{"index": 0, "embedding": [1.0, 0.0]}]}, expected_count=1)
    with pytest.raises(vector_recall.EmbeddingContractError):
        embedder._vectors({"data": []}, expected_count=1)
    with pytest.raises(vector_recall.EmbeddingContractError):
        embedder._vectors({"error": {"message": "arrears"}}, expected_count=1)


def test_openai_backend_requires_key_and_fails_open(monkeypatch) -> None:
    monkeypatch.delenv("MISSING_TEST_KEY", raising=False)
    vector_recall._EMBED_CACHE.clear()
    lexical = [{"node_id": "a", "score": 1.0, "node": _node("a", "text")}]
    out = vector_recall.fuse(
        "query",
        lexical,
        top_k=5,
        candidates_provider=lambda: [_node("b", "coffee")],
        cfg=_dense_cfg(
            vector_recall_backend="openai",
            vector_recall_api_key_env="MISSING_TEST_KEY",
        ),
    )
    assert out is lexical


def test_openai_backend_dispatches_through_dense_ranking(monkeypatch) -> None:
    fake = _FakeEmbedder()
    monkeypatch.setattr(vector_recall, "_make_embedder", lambda _evomem: fake)
    vector_recall._EMBED_CACHE.clear()
    out = vector_recall.fuse(
        "coffee",
        [],
        top_k=1,
        candidates_provider=lambda: [_node("n-tea", "tea"), _node("n-coffee", "coffee")],
        cfg=_dense_cfg(vector_recall_backend="openai"),
    )
    assert [h["node_id"] for h in out] == ["n-coffee"]
