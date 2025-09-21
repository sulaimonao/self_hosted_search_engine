"""Thin HTTP client around the Ollama REST API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

import requests


class OllamaClientError(RuntimeError):
    """Raised when the Ollama API returns an unexpected response."""


@dataclass(slots=True)
class ChatMessage:
    role: str
    content: str


class OllamaClient:
    """Minimal HTTP wrapper that exposes chat and embedding helpers."""

    def __init__(self, base_url: str, timeout: float = 60.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()

    # ------------------------------------------------------------------
    # Chat completions
    # ------------------------------------------------------------------
    def chat(self, model: str, messages: Sequence[ChatMessage], options: dict | None = None) -> str:
        payload = {
            "model": model,
            "messages": [message.__dict__ for message in messages],
            "stream": False,
        }
        if options:
            payload["options"] = options
        response = self._session.post(
            f"{self.base_url}/api/chat",
            json=payload,
            timeout=self.timeout,
        )
        try:
            response.raise_for_status()
        except requests.RequestException as exc:  # pragma: no cover - network failure
            raise OllamaClientError(str(exc)) from exc
        try:
            data = response.json()
        except ValueError as exc:  # pragma: no cover - unexpected response
            raise OllamaClientError("Invalid JSON response from Ollama") from exc
        message = data.get("message") or {}
        content = message.get("content") or data.get("response")
        if not isinstance(content, str):
            raise OllamaClientError("Unexpected chat response payload")
        return content

    # ------------------------------------------------------------------
    # Embeddings
    # ------------------------------------------------------------------
    def embed(self, model: str, texts: Sequence[str]) -> list[list[float]]:
        embeddings: list[list[float]] = []
        for text in texts:
            payload = {"model": model, "prompt": text}
            response = self._session.post(
                f"{self.base_url}/api/embeddings",
                json=payload,
                timeout=self.timeout,
            )
            try:
                response.raise_for_status()
            except requests.RequestException as exc:  # pragma: no cover - network failure
                raise OllamaClientError(str(exc)) from exc
            try:
                data = response.json()
            except ValueError as exc:  # pragma: no cover - unexpected response
                raise OllamaClientError("Invalid JSON response from Ollama") from exc
            vector = data.get("embedding")
            if not isinstance(vector, Iterable):
                raise OllamaClientError("Unexpected embedding response payload")
            embeddings.append([float(value) for value in vector])
        return embeddings

    def embed_one(self, model: str, text: str) -> list[float]:
        [vector] = self.embed(model, [text])
        return vector

    # ------------------------------------------------------------------
    # Model discovery helpers
    # ------------------------------------------------------------------
    def list_models(self) -> list[str]:
        """Return the names of models available on the Ollama instance."""

        try:
            response = self._session.get(
                f"{self.base_url}/api/tags", timeout=self.timeout
            )
            response.raise_for_status()
        except requests.RequestException as exc:  # pragma: no cover - network failure
            raise OllamaClientError(str(exc)) from exc
        try:
            payload = response.json()
        except ValueError as exc:  # pragma: no cover - unexpected response
            raise OllamaClientError("Invalid JSON response from Ollama") from exc
        models: list[str] = []
        for item in payload.get("models", []):
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if isinstance(name, str) and name:
                models.append(name)
        return models

    def has_model(self, model: str) -> bool:
        """Return ``True`` when the named model is available locally."""

        if not model:
            return False
        try:
            available = self.list_models()
        except OllamaClientError:
            return False
        return model in available


__all__ = ["OllamaClient", "OllamaClientError", "ChatMessage"]
