"""Embedding helpers backed by Ollama models."""

from __future__ import annotations

from typing import Sequence

from ..llm.ollama_client import OllamaClient, OllamaClientError


class EmbeddingError(RuntimeError):
    """Raised when embeddings cannot be generated."""


class OllamaEmbedder:
    """Turns text into vectors using Ollama's embedding endpoint."""

    def __init__(self, client: OllamaClient, model: str) -> None:
        self._client = client
        self._model = model

    @property
    def model(self) -> str:
        """Return the active embedding model name."""

        return self._model

    def set_model(self, model: str) -> None:
        """Update the active embedding model name."""

        self._model = model

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            return self._client.embed(self._model, texts)
        except OllamaClientError as exc:  # pragma: no cover - network failures
            raise EmbeddingError(str(exc)) from exc

    def embed_query(self, text: str) -> list[float]:
        vectors = self.embed_documents([text])
        return vectors[0] if vectors else []


__all__ = ["OllamaEmbedder", "EmbeddingError"]
