"""Thin HTTP client around the Ollama REST API."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from typing import Any, Iterable, Mapping, Sequence

import requests

from observability import start_span


class OllamaClientError(RuntimeError):
    """Raised when the Ollama API returns an unexpected response."""


@dataclass(slots=True)
class ChatMessage:
    role: str
    content: str


def _message_to_dict(message: Any) -> dict[str, str]:
    """Normalize chat messages into the Ollama payload structure."""

    data: Any
    if isinstance(message, Mapping):
        data = dict(message)
    elif is_dataclass(message):
        data = asdict(message)
    elif hasattr(message, "model_dump") and callable(message.model_dump):
        data = message.model_dump()
    else:
        data = {
            "role": getattr(message, "role", None),
            "content": getattr(message, "content", None),
        }

    if not isinstance(data, Mapping):
        raise OllamaClientError("Invalid chat message payload")

    role = data.get("role")
    content = data.get("content")
    if not isinstance(role, str) or not isinstance(content, str):
        raise OllamaClientError("Invalid chat message payload")

    return {"role": role, "content": content}


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
            "messages": [_message_to_dict(message) for message in messages],
            "stream": False,
        }
        if options:
            payload["options"] = options
        with start_span(
            "ollama.chat",
            attributes={"llm.model": model},
            inputs={"message_count": len(messages)},
        ) as span:
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
            content = content.strip()
            if not content:
                raise OllamaClientError("Empty chat response payload")
            if span is not None:
                span.set_attribute("llm.response_chars", len(content))
            return content

    # ------------------------------------------------------------------
    # Embeddings
    # ------------------------------------------------------------------
    def embed(self, model: str, texts: Sequence[str]) -> list[list[float]]:
        embeddings: list[list[float]] = []
        with start_span(
            "ollama.embed",
            attributes={"llm.model": model, "text.count": len(texts)},
        ) as span:
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
            if span is not None and embeddings:
                span.set_attribute("embedding.dims", len(embeddings[0]))
            return embeddings

    def embed_one(self, model: str, text: str) -> list[float]:
        [vector] = self.embed(model, [text])
        return vector

    # ------------------------------------------------------------------
    # Model discovery helpers
    # ------------------------------------------------------------------
    def list_models(self) -> list[str]:
        """Return the names of models available on the Ollama instance."""

        with start_span("ollama.list_models", attributes={"ollama.host": self.base_url}) as span:
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
            if span is not None:
                span.set_attribute("ollama.model_count", len(models))
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
