"""Helpers for querying the Learned Web discovery cache."""

from __future__ import annotations

import json
import math
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence

import re


_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


def _safe_float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _norm(vector: Sequence[float]) -> float:
    return math.sqrt(sum(component * component for component in vector))


def _cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if not left or not right:
        return 0.0
    limit = min(len(left), len(right))
    if limit == 0:
        return 0.0
    dot = 0.0
    for idx in range(limit):
        dot += left[idx] * right[idx]
    if dot <= 0.0:
        return 0.0
    left_norm = _norm(left[:limit])
    right_norm = _norm(right[:limit])
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / (left_norm * right_norm)


def _tokenize(text: str) -> List[str]:
    return [token.lower() for token in _TOKEN_RE.findall(text or "") if token]


def _hashed_embedding(tokens: Iterable[str], *, dimension: int) -> List[float]:
    vector = [0.0] * dimension
    for token in tokens:
        bucket = hash(token) % dimension
        vector[bucket] += 1.0
    norm = _norm(vector)
    if norm == 0.0:
        return vector
    return [component / norm for component in vector]


def _parse_embedding(payload: object) -> List[float]:
    if payload is None:
        return []
    if isinstance(payload, (bytes, bytearray)):
        try:
            payload = payload.decode("utf-8")
        except UnicodeDecodeError:
            # Treat raw float array payloads as zero vectors.
            return []
    if isinstance(payload, str):
        payload = payload.strip()
        if not payload:
            return []
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return []
    else:
        data = payload
    if isinstance(data, list):
        return [_safe_float(component) for component in data]
    return []


@dataclass
class LearnedWebStore:
    """Lightweight interface for the Learned Web SQLite database."""

    path: Path
    dimension: int = 256

    def __post_init__(self) -> None:
        self._lock = threading.Lock()

    def embed(self, text: str) -> List[float]:
        tokens = _tokenize(text)
        if not tokens:
            return [0.0] * self.dimension
        return _hashed_embedding(tokens, dimension=self.dimension)

    def similar_urls(
        self,
        query: str,
        *,
        limit: int,
        min_similarity: float,
    ) -> List[str]:
        query = (query or "").strip()
        if not query or limit <= 0:
            return []
        if not self.path.exists():
            return []

        try:
            vector = self.embed(query)
        except Exception:
            return []

        with self._lock:
            try:
                connection = sqlite3.connect(str(self.path))
            except sqlite3.Error:
                return []
            try:
                connection.row_factory = sqlite3.Row
                cursor = connection.execute(
                    """
                    SELECT url, embedding
                    FROM discoveries
                    WHERE embedding IS NOT NULL
                    ORDER BY updated_at DESC
                    LIMIT 512
                    """
                )
                candidates: list[tuple[float, str]] = []
                for row in cursor:
                    if isinstance(row, sqlite3.Row):
                        mapping = dict(row)
                        url = mapping.get("url")
                        embedding = mapping.get("embedding")
                    else:
                        url = row[0]
                        embedding = row[1]
                    parsed = _parse_embedding(embedding)
                    if not parsed:
                        continue
                    similarity = _cosine_similarity(vector, parsed)
                    if similarity < min_similarity:
                        continue
                    if isinstance(url, str) and url.strip():
                        candidates.append((similarity, url.strip()))
            except sqlite3.Error:
                return []
            finally:
                connection.close()

        candidates.sort(key=lambda item: item[0], reverse=True)
        seen: set[str] = set()
        ordered: list[str] = []
        for similarity, url in candidates:
            if url in seen:
                continue
            seen.add(url)
            ordered.append(url)
            if len(ordered) >= limit:
                break
        return ordered


__all__ = ["LearnedWebStore"]

