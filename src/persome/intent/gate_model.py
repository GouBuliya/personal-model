"""Deprecated compatibility facade for the neutral local embedding runtime."""

from ..retrieval.local_embeddings import (
    _Engine,
    _get_engine,
    _model_dir,
    _models_root,
    available,
    default_threshold,
    score,
)

__all__ = [
    "_Engine",
    "_get_engine",
    "_model_dir",
    "_models_root",
    "available",
    "default_threshold",
    "score",
]
