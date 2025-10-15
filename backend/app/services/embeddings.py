"""Helpers for embedding lookups and caching via the Ollama API."""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Sequence

import numpy as np
import requests


OLLAMA = "http://127.0.0.1:11434"
EMBED_MODEL = "embeddinggemma"


def _hash_key(text: str) -> str:
    """Return a stable content fingerprint for ``text``."""

    return hashlib.sha256(text.encode("utf-8"), usedforsecurity=False).hexdigest()


def to_blob(vec: Sequence[float]) -> bytes:
    """Serialize a vector into a ``BLOB`` suitable for SQLite storage."""

    return np.asarray(tuple(vec), dtype=np.float32).tobytes()


def from_blob(blob: bytes) -> np.ndarray:
    """Deserialize a ``BLOB`` created via :func:`to_blob`."""

    return np.frombuffer(blob, dtype=np.float32)


def embed_texts(texts: Sequence[str]) -> list[list[float]]:
    """Call the Ollama embeddings endpoint for ``EMBED_MODEL``."""

    if not texts:
        return []

    response = requests.post(
        f"{OLLAMA}/api/embeddings",
        json={"model": EMBED_MODEL, "input": list(texts)},
        timeout=120,
    )
    response.raise_for_status()
    data = response.json()

    if "embeddings" in data:
        return data["embeddings"]
    if "embedding" in data:  # single input fallback
        return [data["embedding"]]
    raise RuntimeError(f"Unexpected embeddings response: {data}")


def ensure_embedding_cache(conn: sqlite3.Connection) -> None:
    """Ensure the ``embedding_cache`` table exists on ``conn``."""

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS embedding_cache (
            key TEXT PRIMARY KEY,
            dim INTEGER,
            vec BLOB
        );
        """
    )


def _extract_blob(row: sqlite3.Row | tuple[bytes] | tuple[bytes, ...]) -> bytes:
    if isinstance(row, sqlite3.Row):
        return row["vec"]
    return row[0]


def get_or_embed(conn: sqlite3.Connection, key: str, text: str) -> np.ndarray:
    """Return an embedding for ``text`` using ``key`` as the cache identifier."""

    row = conn.execute("SELECT vec FROM embedding_cache WHERE key=?", (key,)).fetchone()
    if row is not None:
        return from_blob(_extract_blob(row))

    [vec] = embed_texts([text])
    conn.execute(
        "INSERT OR REPLACE INTO embedding_cache(key, dim, vec) VALUES (?,?,?)",
        (key, len(vec), to_blob(vec)),
    )
    conn.commit()
    return np.asarray(vec, dtype=np.float32)


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity with defensive normalisation."""

    aa = float(np.linalg.norm(a) + 1e-8)
    bb = float(np.linalg.norm(b) + 1e-8)
    return float(np.dot(a, b) / (aa * bb))


def content_fingerprint(text: str) -> str:
    """Return the deterministic fingerprint used for dedupe."""

    return _hash_key(text)


__all__ = [
    "embed_texts",
    "ensure_embedding_cache",
    "get_or_embed",
    "cosine",
    "content_fingerprint",
    "to_blob",
    "from_blob",
]
