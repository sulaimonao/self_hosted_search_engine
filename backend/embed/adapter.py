"""Embedding helper bridging to Ollama's EmbeddingGemma endpoint."""

from __future__ import annotations

import logging
import os
from typing import Iterable, List, Sequence

import httpx

LOGGER = logging.getLogger(__name__)
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
DEFAULT_EMBED_MODEL = "embeddinggemma"


def _canonicalize_model(model: str | None) -> str:
    """Return the canonical Ollama slug for the configured embedding model."""

    if not model:
        return DEFAULT_EMBED_MODEL
    slug = str(model).strip()
    if not slug:
        return DEFAULT_EMBED_MODEL
    normalized = slug.lower().replace("-", "").replace("_", "")
    if normalized == DEFAULT_EMBED_MODEL:
        return DEFAULT_EMBED_MODEL
    return slug


EMBED_MODEL = _canonicalize_model(os.getenv("EMBED_MODEL", DEFAULT_EMBED_MODEL))


def _normalize_payload(response_json: dict) -> List[List[float]] | None:
    if not isinstance(response_json, dict):
        return None
    if "data" in response_json:
        data = response_json.get("data")
        if isinstance(data, list):
            embeddings: List[List[float]] = []
            for item in data:
                vector = item.get("embedding") if isinstance(item, dict) else None
                if isinstance(vector, Sequence):
                    embeddings.append([float(v) for v in vector])
            return embeddings if embeddings else None
    embedding = response_json.get("embedding")
    if isinstance(embedding, Sequence):
        return [[float(v) for v in embedding]]
    return None


def embed_texts(texts: Iterable[str]) -> List[List[float]] | None:
    payload_texts = [text for text in (str(t).strip() for t in texts) if text]
    if not payload_texts:
        return []
    try:
        response = httpx.post(
            f"{OLLAMA_URL}/api/embeddings",
            json={"model": EMBED_MODEL, "input": payload_texts},
            timeout=60,
        )
        response.raise_for_status()
    except Exception as exc:  # pragma: no cover - network failures collapse to fallback
        LOGGER.warning("embedding request failed: %s", exc)
        return None
    try:
        data = response.json()
    except ValueError as exc:  # pragma: no cover - defensive guard
        LOGGER.warning("invalid embedding response: %s", exc)
        return None
    vectors = _normalize_payload(data)
    if vectors is None:
        LOGGER.debug("embedding adapter falling back due to empty vectors")
    return vectors


__all__ = ["embed_texts", "EMBED_MODEL", "OLLAMA_URL"]
