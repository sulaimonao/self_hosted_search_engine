"""Lightweight query embedding helpers used by :mod:`SearchService`."""

from __future__ import annotations

import hashlib
import math
import re
from typing import Sequence

__all__ = ["embed_query", "cosine_similarity"]

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    """Return lowercase alphanumeric tokens extracted from *text*."""

    if not text:
        return []
    return _TOKEN_RE.findall(text.lower())


def _bucket_index(token: str, dimensions: int) -> int:
    digest = hashlib.sha256(token.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % dimensions


def embed_query(text: str, *, dimensions: int = 64) -> list[float]:
    """Return a deterministic embedding vector for ``text``.

    The implementation intentionally avoids external dependencies so unit tests
    remain lightweight.  Tokens are hashed into a fixed-size bucketed vector and
    L2 normalised, which is sufficient for cosine similarity comparisons when
    bootstrapping frontiers from past discoveries.
    """

    dims = max(8, int(dimensions))
    vector = [0.0] * dims
    tokens = _tokenize(text)
    if not tokens:
        return vector
    for token in tokens:
        idx = _bucket_index(token, dims)
        vector[idx] += 1.0
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    """Return the cosine similarity between two vectors."""

    if not left or not right:
        return 0.0
    length = min(len(left), len(right))
    if length == 0:
        return 0.0
    dot = 0.0
    left_norm = 0.0
    right_norm = 0.0
    for idx in range(length):
        lv = float(left[idx])
        rv = float(right[idx])
        dot += lv * rv
        left_norm += lv * lv
        right_norm += rv * rv
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    denominator = math.sqrt(left_norm) * math.sqrt(right_norm)
    if denominator == 0.0:
        return 0.0
    return max(-1.0, min(dot / denominator, 1.0))

