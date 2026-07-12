"Local hashed n-gram vector recall fused with the lexical recall path."

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from collections.abc import Callable
from typing import Any

from ..logger import get

_log = get("persome.evomem")

# Sparse hashed feature space. Large enough that collisions stay rare for a
# personal-scale library; no model download, fully deterministic and offline.
_DIM = 1 << 18
_ASCII_TOKEN_RE = re.compile(r"[a-z0-9]{2,}")
_CJK_RE = re.compile("[\u3400-\u9fff\uf900-\ufaff]")
_RRF_K = 60  # standard reciprocal-rank-fusion damping constant
_MAX_CANDIDATES = 512  # cap embedding work per query
_MIN_SIMILARITY = 0.05  # drop near-orthogonal vector hits instead of ranking noise

CandidatesProvider = Callable[[], list[Any]]


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


def _enabled(cfg: Any) -> bool:
    if cfg is None:
        from .. import config as config_mod

        cfg = config_mod.load()
    evomem = getattr(cfg, "evomem", cfg)
    return bool(getattr(evomem, "vector_recall_enabled", False))


def _vector_ranking(query: str, candidates: list[Any], *, top_k: int) -> list[Any]:
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


def fuse(
    query: str,
    lexical_hits: list[dict],
    *,
    top_k: int,
    candidates_provider: CandidatesProvider,
    cfg: Any | None = None,
) -> list[dict]:
    """Fuse lexical hits with local vector recall via reciprocal-rank fusion.

    Disabled (the default), an empty query vector, or any internal failure
    returns ``lexical_hits`` unchanged, so the deterministic lexical path stays
    the safe baseline. Enabled, paraphrased memories that share no full token
    with the query can still surface through hashed n-gram similarity.
    """
    try:
        if not _enabled(cfg):
            return lexical_hits
        vector_nodes = _vector_ranking(query, candidates_provider(), top_k=top_k)
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
