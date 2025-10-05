import hashlib
from typing import List

import numpy as np
import requests
import sqlite3


OLLAMA = "http://127.0.0.1:11434"
EMBED_MODEL = "embeddinggemma"


def _hash_key(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def to_blob(vec: List[float]) -> bytes:
    return np.asarray(vec, dtype=np.float32).tobytes()


def from_blob(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)


def embed_texts(texts: List[str]) -> List[List[float]]:
    """Call Ollama embeddings for embeddinggemma.

    Returns a list of float vectors.
    """

    if not texts:
        return []

    r = requests.post(
        f"{OLLAMA}/api/embeddings",
        json={"model": EMBED_MODEL, "input": texts},
        timeout=120,
    )
    r.raise_for_status()
    data = r.json()

    if "embeddings" in data:
        return data["embeddings"]

    if "embedding" in data:  # single input fallback
        return [data["embedding"]]

    raise RuntimeError(f"Unexpected embeddings response: {data}")


def ensure_embedding_cache(conn: sqlite3.Connection):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS embedding_cache (
            key TEXT PRIMARY KEY,
            dim INTEGER,
            vec BLOB
        );
        """
    )


def get_or_embed(conn: sqlite3.Connection, key: str, text: str) -> np.ndarray:
    row = conn.execute("SELECT vec FROM embedding_cache WHERE key=?", (key,)).fetchone()
    if row:
        return from_blob(row["vec"])

    [vec] = embed_texts([text])
    conn.execute(
        "INSERT OR REPLACE INTO embedding_cache(key, dim, vec) VALUES (?,?,?)",
        (key, len(vec), to_blob(vec)),
    )
    conn.commit()
    return np.array(vec, dtype=np.float32)


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    aa = float(np.linalg.norm(a) + 1e-8)
    bb = float(np.linalg.norm(b) + 1e-8)
    return float(np.dot(a, b) / (aa * bb))


def content_fingerprint(text: str) -> str:
    return _hash_key(text)
