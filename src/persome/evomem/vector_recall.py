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


def _make_embedder(evomem: Any) -> OllamaEmbedder:
    return OllamaEmbedder(
        base_url=str(getattr(evomem, "vector_recall_ollama_url", "http://127.0.0.1:11434")),
        model=str(getattr(evomem, "vector_recall_model", "nomic-embed-text")),
        expected_dimension=int(getattr(evomem, "vector_recall_dimension", 768)),
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


# ── fusion ───────────────────────────────────────────────────────────────────


def _evomem_cfg(cfg: Any) -> Any:
    if cfg is None:
        from .. import config as config_mod

        cfg = config_mod.load()
    return getattr(cfg, "evomem", cfg)


def _vector_ranking(query: str, candidates: list[Any], *, top_k: int, evomem: Any) -> list[Any]:
    backend = str(getattr(evomem, "vector_recall_backend", "hash")).strip().lower()
    if backend == "ollama":
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
        vector_nodes = _vector_ranking(query, candidates_provider(), top_k=top_k, evomem=evomem)
        if not vector_nodes:
            return lexical_hits

        fused: dict[str, dict] = {}
        for rank, hit in enumerate(lexical_hits):
            entry = {"node_id": hit["node_id"], "score": 0.0, "node": hit["node"]}
            entry["score"] += 1.0 / (_RRF_K + rank + 1)
            fused[hit["node_id"]] = entry
        for rank, node in enumerate(vector_nodes):
            entry = fused.setdefault(
                node.node_id, {"node_id": node.node_id, "score": 0.0, "node": node}
            )
            entry["score"] += 1.0 / (_RRF_K + rank + 1)

        ranked = sorted(fused.values(), key=lambda item: (-item["score"], item["node_id"]))
        return ranked[:top_k]
    except Exception:  # noqa: BLE001 — recall must never break on the vector side
        _log.debug("vector_recall: fuse failed; falling back to lexical hits", exc_info=True)
        return lexical_hits
