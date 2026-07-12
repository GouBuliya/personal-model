"Local vector recall (hashed n-gram or Ollama dense) fused with lexical recall."

from __future__ import annotations

import hashlib
import json
import math
import re
import threading
import unicodedata
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..logger import get

_log = get("persome.evomem")

# Sparse hashed feature space. Large enough that collisions stay rare for a
# personal-scale library; no model download, fully deterministic and offline.
_DIM = 1 << 18
_ASCII_TOKEN_RE = re.compile(r"[a-z0-9]{2,}")
_CJK_RE = re.compile(f"[{chr(0x3400)}-{chr(0x9FFF)}{chr(0xF900)}-{chr(0xFAFF)}]")
_RRF_K = 60  # standard reciprocal-rank-fusion damping constant
_MAX_CANDIDATES = 512  # cap embedding work per query
_MIN_SIMILARITY = 0.05  # drop near-orthogonal hash hits instead of ranking noise
_EMBED_BATCH = 64  # cap texts per Ollama request
_CACHE_MAX = 4096  # process-local dense-vector cache entries

CandidatesProvider = Callable[[], list[Any]]


# ── hashed n-gram backend (offline default) ─────────────────────────────────


def _bucket(feature: str) -> int:
    digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") % _DIM


def _features(text: str) -> list[str]:
    """ASCII word tokens plus CJK unigrams and bigrams from normalized text."""
    folded = unicodedata.normalize("NFKC", text or "").casefold()
    feats = _ASCII_TOKEN_RE.findall(folded)
    cjk = _CJK_RE.findall(folded)
    feats.extend(cjk)
    feats.extend(a + b for a, b in zip(cjk, cjk[1:], strict=False))
    return feats


def embed(text: str) -> dict[int, float]:
    """L2-normalized sparse term-frequency vector over hashed features."""
    counts: dict[int, float] = {}
    for feature in _features(text):
        key = _bucket(feature)
        counts[key] = counts.get(key, 0.0) + 1.0
    norm = math.sqrt(sum(v * v for v in counts.values()))
    if norm == 0.0:
        return {}
    return {k: v / norm for k, v in counts.items()}


def cosine(a: dict[int, float], b: dict[int, float]) -> float:
    if len(b) < len(a):
        a, b = b, a
    return sum(v * b.get(k, 0.0) for k, v in a.items())


def _hash_ranking(query: str, candidates: list[Any], *, top_k: int) -> list[Any]:
    query_vec = embed(query)
    if not query_vec:
        return []
    scored: list[tuple[float, str, Any]] = []
    for node in candidates[:_MAX_CANDIDATES]:
        similarity = cosine(query_vec, embed(getattr(node, "content", "") or ""))
        if similarity >= _MIN_SIMILARITY:
            scored.append((similarity, node.node_id, node))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [node for _, _, node in scored[:top_k]]


# ── Ollama dense backend ─────────────────────────────────────────────────────
# Embedding client adapted from persome-bench's retrieval module (same author),
# keeping its strict response-contract validation.


class EmbeddingContractError(RuntimeError):
    """The configured embedding service violated the expected contract."""


@dataclass(frozen=True)
class OllamaEmbedder:
    base_url: str = "http://127.0.0.1:11434"
    model: str = "nomic-embed-text"
    expected_dimension: int = 768
    timeout_seconds: float = 60.0

    def _request(self, texts: list[str]) -> dict[str, Any]:
        request = urllib.request.Request(
            f"{self.base_url.rstrip('/')}/api/embed",
            data=json.dumps({"model": self.model, "input": texts}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310 — owner-configured local endpoint
            return json.load(response)

    def _vectors(self, payload: dict[str, Any], *, expected_count: int) -> list[list[float]]:
        raw = payload.get("embeddings")
        if not isinstance(raw, list) or len(raw) != expected_count:
            raise EmbeddingContractError(
                f"Ollama returned {len(raw) if isinstance(raw, list) else 'invalid'} "
                f"embeddings for {expected_count} inputs"
            )
        vectors: list[list[float]] = []
        for index, vector in enumerate(raw):
            if not isinstance(vector, list) or len(vector) != self.expected_dimension:
                raise EmbeddingContractError(
                    f"embedding {index} dimension is "
                    f"{len(vector) if isinstance(vector, list) else 'invalid'}, "
                    f"expected {self.expected_dimension}"
                )
            try:
                vectors.append([float(value) for value in vector])
            except (TypeError, ValueError) as exc:
                raise EmbeddingContractError(
                    f"embedding {index} contains a non-numeric value"
                ) from exc
        return vectors

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors: list[list[float]] = []
        for start in range(0, len(texts), _EMBED_BATCH):
            chunk = texts[start : start + _EMBED_BATCH]
            vectors.extend(self._vectors(self._request(chunk), expected_count=len(chunk)))
        return vectors

    def embed(self, text: str) -> list[float]:
        return self.embed_batch([text])[0]


@dataclass(frozen=True)
class OpenAICompatibleEmbedder:
    """OpenAI-protocol /embeddings client (OpenAI, DashScope, aggregators).

    Mirrors the legacy runtime's cloud-embedding route: the endpoint and model
    live in config, the key VALUE lives only in the environment (loaded from
    ``<PERSOME_ROOT>/env`` by the daemon) under ``api_key_env``.
    """

    base_url: str = "https://api.openai.com/v1"
    model: str = "text-embedding-3-large"
    expected_dimension: int = 3072
    api_key_env: str = "OPENAI_API_KEY"
    timeout_seconds: float = 60.0

    def _endpoint(self) -> tuple[str, dict[str, str]]:
        """Resolve the POST URL and auth header for both endpoint shapes.

        Mirrors the legacy runtime's embeddings client: a base URL that already
        names the route (Azure ``.../deployments/<dep>/embeddings?api-version=...``
        or anything ending in ``/embeddings``) is used verbatim with Azure's
        ``api-key`` header; a plain base gets ``/embeddings`` appended and the
        standard ``Authorization: Bearer`` header.
        """
        import os

        key = (os.environ.get(self.api_key_env) or "").strip()
        if not key:
            raise EmbeddingContractError(f"{self.api_key_env} is not set in the environment")
        low = self.base_url.lower()
        is_full = (
            "/deployments/" in low
            or "api-version=" in low
            or low.rstrip("/").endswith("/embeddings")
        )
        if is_full:
            if "azure" in low or "cognitiveservices" in low:
                return self.base_url, {"api-key": key}
            return self.base_url, {"Authorization": f"Bearer {key}"}
        return f"{self.base_url.rstrip('/')}/embeddings", {"Authorization": f"Bearer {key}"}

    def _request(self, texts: list[str]) -> dict[str, Any]:
        url, auth = self._endpoint()
        request = urllib.request.Request(
            url,
            data=json.dumps({"model": self.model, "input": texts}).encode(),
            headers={"Content-Type": "application/json", **auth},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310 - owner-configured endpoint
            return json.load(response)

    def _vectors(self, payload: dict[str, Any], *, expected_count: int) -> list[list[float]]:
        rows = payload.get("data")
        if not isinstance(rows, list) or len(rows) != expected_count:
            raise EmbeddingContractError(
                f"endpoint returned {len(rows) if isinstance(rows, list) else 'invalid'} "
                f"embeddings for {expected_count} inputs"
            )
        ordered = sorted(rows, key=lambda item: int(item.get("index", 0)))
        vectors: list[list[float]] = []
        for index, row in enumerate(ordered):
            vector = row.get("embedding") if isinstance(row, dict) else None
            if not isinstance(vector, list) or len(vector) != self.expected_dimension:
                raise EmbeddingContractError(
                    f"embedding {index} dimension is "
                    f"{len(vector) if isinstance(vector, list) else 'invalid'}, "
                    f"expected {self.expected_dimension}"
                )
            try:
                vectors.append([float(value) for value in vector])
            except (TypeError, ValueError) as exc:
                raise EmbeddingContractError(
                    f"embedding {index} contains a non-numeric value"
                ) from exc
        return vectors

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors: list[list[float]] = []
        # Conservative chunking: some compatible vendors cap batches at 10.
        for start in range(0, len(texts), 10):
            chunk = texts[start : start + 10]
            vectors.extend(self._vectors(self._request(chunk), expected_count=len(chunk)))
        return vectors

    def embed(self, text: str) -> list[float]:
        return self.embed_batch([text])[0]


def _cosine_dense(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


# (model, node_id) -> (content digest, embedding). Process-local: recall runs in
# the long-lived daemon, so warm queries embed only the query text.
_cache_lock = threading.Lock()
_EMBED_CACHE: dict[tuple[str, str], tuple[str, list[float]]] = {}


def _content_digest(text: str) -> str:
    return hashlib.blake2b(text.encode("utf-8"), digest_size=16).hexdigest()


def _make_embedder(evomem: Any) -> Any:
    backend = str(getattr(evomem, "vector_recall_backend", "hash")).strip().lower()
    if backend == "openai":
        return OpenAICompatibleEmbedder(
            base_url=str(getattr(evomem, "vector_recall_openai_url", "https://api.openai.com/v1")),
            model=str(getattr(evomem, "vector_recall_model", "text-embedding-3-large")),
            expected_dimension=int(getattr(evomem, "vector_recall_dimension", 3072)),
            api_key_env=str(getattr(evomem, "vector_recall_api_key_env", "OPENAI_API_KEY")),
        )
    return OllamaEmbedder(
        base_url=str(getattr(evomem, "vector_recall_ollama_url", "http://127.0.0.1:11434")),
        model=str(getattr(evomem, "vector_recall_model", "bge-m3")),
        expected_dimension=int(getattr(evomem, "vector_recall_dimension", 1024)),
    )


def _dense_ranking(
    query: str,
    candidates: list[Any],
    *,
    top_k: int,
    evomem: Any,
    embedder: Any | None = None,
) -> list[Any]:
    embedder = embedder if embedder is not None else _make_embedder(evomem)
    pool = candidates[:_MAX_CANDIDATES]

    missing: list[tuple[tuple[str, str], str, str]] = []  # (cache key, digest, text)
    with _cache_lock:
        for node in pool:
            content = getattr(node, "content", "") or ""
            key = (embedder.model, node.node_id)
            digest = _content_digest(content)
            cached = _EMBED_CACHE.get(key)
            if cached is None or cached[0] != digest:
                missing.append((key, digest, content))
    if missing:
        vectors = embedder.embed_batch([text for _, _, text in missing])
        with _cache_lock:
            for (key, digest, _text), vector in zip(missing, vectors, strict=True):
                _EMBED_CACHE[key] = (digest, vector)
            while len(_EMBED_CACHE) > _CACHE_MAX:
                _EMBED_CACHE.pop(next(iter(_EMBED_CACHE)))

    query_vec = embedder.embed(query)
    scored: list[tuple[float, str, Any]] = []
    with _cache_lock:
        for node in pool:
            cached = _EMBED_CACHE.get((embedder.model, node.node_id))
            if cached is None:
                continue
            scored.append((_cosine_dense(query_vec, cached[1]), node.node_id, node))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [node for _, _, node in scored[:top_k]]


# ── weighted fusion, diversity, and query expansion (persome-bench ports) ────


def _clean_weight(value: Any) -> float:
    try:
        weight = float(value)
    except (TypeError, ValueError):
        return 1.0
    return weight if math.isfinite(weight) and weight >= 0.0 else 1.0


def _head_weights(evomem: Any) -> tuple[float, float]:
    return (
        _clean_weight(getattr(evomem, "vector_recall_lexical_weight", 1.0)),
        _clean_weight(getattr(evomem, "vector_recall_vector_weight", 1.0)),
    )


def _diversity_lambda(evomem: Any) -> float:
    try:
        value = float(getattr(evomem, "vector_recall_diversity_lambda", 0.0))
    except (TypeError, ValueError):
        return 0.0
    return value if math.isfinite(value) and 0.0 <= value < 1.0 else 0.0


def _mmr_select(ranked: list[dict], *, top_k: int, diversity_lambda: float) -> list[dict]:
    """Deterministic greedy maximal-marginal-relevance selection.

    Ported from persome-bench: relevance is the fused score normalized over
    the pool; redundancy is the maximum feature-set Jaccard similarity against
    already-selected hits. Ties fall back to the fused rank, so
    diversity_lambda=0 degenerates to the plain rank-order prefix.
    """
    if not ranked or diversity_lambda <= 0.0:
        return ranked[:top_k]
    max_score = max(hit["score"] for hit in ranked) or 1.0
    features = {
        hit["node_id"]: set(_features(getattr(hit["node"], "content", "") or "")) for hit in ranked
    }
    order = {hit["node_id"]: index for index, hit in enumerate(ranked)}
    selected: list[dict] = []
    remaining = list(ranked)
    while remaining and len(selected) < top_k:
        best: dict | None = None
        best_key: tuple[float, int] | None = None
        for hit in remaining:
            terms = features[hit["node_id"]]
            redundancy = 0.0
            for chosen in selected:
                chosen_terms = features[chosen["node_id"]]
                union = len(terms | chosen_terms)
                if union:
                    redundancy = max(redundancy, len(terms & chosen_terms) / union)
            adjusted = hit["score"] / max_score - diversity_lambda * redundancy
            key = (-adjusted, order[hit["node_id"]])
            if best_key is None or key < best_key:
                best = hit
                best_key = key
        assert best is not None
        selected.append(best)
        remaining.remove(best)
    return selected


# Ported verbatim from persome-bench: two retrieval views, one per line.
_QUERY_REWRITE_PROMPT = (
    "Rewrite the question as two retrieval views, one per line. Line 1: the "
    "single declarative statement that would answer it, written about USER "
    "in the third person, preserving every name, place, number, and date "
    "from the question, resolving nothing new and not answering or "
    "inventing facts - leave the unknown quantity implicit. Line 2: the "
    "distinctive retrieval keywords of the question (names, places, "
    "objects, activities, dates), space-separated, no generic words. "
    "Return only these two lines."
)
_REWRITE_MAX_CHARS = 600
_REWRITE_CACHE_MAX = 256
_rewrite_lock = threading.Lock()
_REWRITE_CACHE: dict[str, str] = {}


def expand_query(query: str, cfg: Any | None = None) -> str:
    """Prepend LLM statement+keyword retrieval views to the query.

    Ported from persome-bench: the expanded text feeds BOTH the lexical and
    vector paths, so the keyword view widens token recall while the statement
    view sharpens dense similarity. Disabled (the default) or on any failure
    the raw query is returned unchanged; rewrites are cached per query text.
    """
    try:
        evomem = _evomem_cfg(cfg)
        if not (
            bool(getattr(evomem, "vector_recall_enabled", False))
            and bool(getattr(evomem, "vector_recall_query_rewrite", False))
        ):
            return query
        text = (query or "").strip()
        if not text:
            return query
        with _rewrite_lock:
            cached = _REWRITE_CACHE.get(text)
        if cached is not None:
            return cached

        from .. import config as config_mod
        from ..writer import llm as llm_mod

        full_cfg = cfg if cfg is not None and hasattr(cfg, "model_for") else config_mod.load()
        response = llm_mod.call_llm(
            full_cfg,
            "vector_recall_rewrite",
            messages=[
                {"role": "system", "content": _QUERY_REWRITE_PROMPT},
                {"role": "user", "content": text},
            ],
        )
        rewritten = (response.choices[0].message.content or "").strip()
        expanded = query
        if rewritten and len(rewritten) <= _REWRITE_MAX_CHARS:
            expanded = f"{rewritten}\n{text}"
        with _rewrite_lock:
            if len(_REWRITE_CACHE) >= _REWRITE_CACHE_MAX:
                _REWRITE_CACHE.pop(next(iter(_REWRITE_CACHE)))
            _REWRITE_CACHE[text] = expanded
        return expanded
    except Exception:  # noqa: BLE001 - recall must never break on the rewrite side
        _log.debug("vector_recall: query rewrite failed; using the raw query", exc_info=True)
        return query


# ── fusion ───────────────────────────────────────────────────────────────────


def _evomem_cfg(cfg: Any) -> Any:
    if cfg is None:
        from .. import config as config_mod

        cfg = config_mod.load()
    return getattr(cfg, "evomem", cfg)


def _vector_ranking(query: str, candidates: list[Any], *, top_k: int, evomem: Any) -> list[Any]:
    backend = str(getattr(evomem, "vector_recall_backend", "hash")).strip().lower()
    if backend in ("ollama", "openai"):
        return _dense_ranking(query, candidates, top_k=top_k, evomem=evomem)
    return _hash_ranking(query, candidates, top_k=top_k)


def fuse(
    query: str,
    lexical_hits: list[dict],
    *,
    top_k: int,
    candidates_provider: CandidatesProvider,
    cfg: Any | None = None,
) -> list[dict]:
    """Fuse lexical hits with local vector recall via reciprocal-rank fusion.

    Disabled (the default), an empty query vector, or any internal failure —
    including an unreachable or contract-violating embedding service — returns
    ``lexical_hits`` unchanged, so the deterministic lexical path stays the
    safe baseline. Enabled, paraphrased memories that share no full token with
    the query can still surface through the configured vector backend.
    """
    try:
        evomem = _evomem_cfg(cfg)
        if not bool(getattr(evomem, "vector_recall_enabled", False)):
            return lexical_hits
        # MMR can only trade a redundant hit for a diverse one that is still in
        # the pool, so with diversity enabled the vector head over-selects and
        # the final top_k cut happens after selection (persome-bench fuses the
        # unfiltered candidate set the same way).
        diversity_lambda = _diversity_lambda(evomem)
        pool_k = top_k if diversity_lambda <= 0.0 else max(top_k * 4, top_k + 8)
        vector_nodes = _vector_ranking(query, candidates_provider(), top_k=pool_k, evomem=evomem)
        if not vector_nodes:
            return lexical_hits

        lexical_weight, vector_weight = _head_weights(evomem)
        fused: dict[str, dict] = {}
        for rank, hit in enumerate(lexical_hits):
            entry = {"node_id": hit["node_id"], "score": 0.0, "node": hit["node"]}
            entry["score"] += lexical_weight / (_RRF_K + rank + 1)
            fused[hit["node_id"]] = entry
        for rank, node in enumerate(vector_nodes):
            entry = fused.setdefault(
                node.node_id, {"node_id": node.node_id, "score": 0.0, "node": node}
            )
            entry["score"] += vector_weight / (_RRF_K + rank + 1)

        ranked = sorted(fused.values(), key=lambda item: (-item["score"], item["node_id"]))
        return _mmr_select(ranked, top_k=top_k, diversity_lambda=diversity_lambda)
    except Exception:  # noqa: BLE001 — recall must never break on the vector side
        _log.debug("vector_recall: fuse failed; falling back to lexical hits", exc_info=True)
        return lexical_hits
