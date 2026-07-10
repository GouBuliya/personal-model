"""Deprecated compatibility facade for :mod:`persome.retrieval.local_embeddings`."""

from ..retrieval.local_embeddings import (
    _reset_cache_for_tests,
    available,
    cosine,
    embed,
    similarity,
)

__all__ = ["_reset_cache_for_tests", "available", "cosine", "embed", "similarity"]
