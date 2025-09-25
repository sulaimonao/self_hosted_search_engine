"""JSON-focused Ollama chat helper used by the planner agent."""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Mapping, Sequence

import requests

LOGGER = logging.getLogger(__name__)


class LLMError(RuntimeError):
    """Raised when the planner LLM cannot complete a request."""


def _env_base_url() -> str:
    for key in ("OLLAMA_JSON_HOST", "OLLAMA_BASE_URL", "OLLAMA_URL", "OLLAMA_HOST"):
        candidate = (os.getenv(key) or "").strip()
        if candidate:
            return candidate.rstrip("/")
    return "http://127.0.0.1:11434"


def _env_model() -> str:
    for key in ("OLLAMA_JSON_MODEL", "OLLAMA_MODEL"):
        candidate = (os.getenv(key) or "").strip()
        if candidate:
            return candidate
    return "llama3.1:8b-instruct"


@dataclass(slots=True)
class ChatMessage:
    role: str
    content: str


class OllamaJSONClient:
    """Small wrapper forcing the Ollama chat endpoint to yield JSON payloads."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        default_model: str | None = None,
        timeout: float = 60.0,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = (base_url or _env_base_url()).rstrip("/")
        self.default_model = default_model or _env_model()
        self.timeout = timeout
        self._session = session or requests.Session()
        self._model_cache: tuple[list[str], float] | None = None

    # ------------------------------------------------------------------
    # Model helpers
    # ------------------------------------------------------------------
    def list_models(self, *, refresh: bool = False) -> list[str]:
        if not refresh and self._model_cache:
            cached, expiry = self._model_cache
            if time.monotonic() < expiry:
                return list(cached)
        try:
            response = self._session.get(
                f"{self.base_url}/api/tags", timeout=self.timeout
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise LLMError(str(exc)) from exc
        try:
            payload = response.json()
        except ValueError as exc:
            raise LLMError("Invalid JSON from Ollama tags endpoint") from exc
        models: list[str] = []
        for item in payload.get("models", []):
            if isinstance(item, str):
                name = item
            elif isinstance(item, Mapping):
                candidate = item.get("name")
                name = candidate if isinstance(candidate, str) else None
            else:
                name = None
            if name:
                cleaned = name.strip()
                if cleaned:
                    models.append(cleaned)
        self._model_cache = (models, time.monotonic() + 30.0)
        return list(models)

    def select_model(self, preferred: str | None = None) -> str:
        candidates = [preferred, self.default_model]
        try:
            available = self.list_models()
        except LLMError:
            available = []
        for candidate in candidates:
            if not candidate:
                continue
            cleaned = candidate.strip()
            if not cleaned:
                continue
            if not available or cleaned in available:
                return cleaned
        return candidates[-1] or _env_model()

    # ------------------------------------------------------------------
    # Chat completions
    # ------------------------------------------------------------------
    def chat_json(
        self,
        messages: Sequence[Mapping[str, str]] | Sequence[ChatMessage],
        *,
        model: str | None = None,
        options: Mapping[str, object] | None = None,
    ) -> Mapping[str, object]:
        resolved_model = self.select_model(model)
        payload = {
            "model": resolved_model,
            "messages": [
                message.__dict__ if isinstance(message, ChatMessage) else dict(message)
                for message in messages
            ],
            "stream": False,
        }
        if options:
            payload["options"] = dict(options)
        LOGGER.debug("planner.llm calling model=%s", resolved_model)
        try:
            response = self._session.post(
                f"{self.base_url}/api/chat", json=payload, timeout=self.timeout
            )
        except requests.RequestException as exc:
            raise LLMError(str(exc)) from exc
        status = response.status_code
        if status == 404:
            raise LLMError(f"HTTP 404 (model not found): {resolved_model}")
        if not (200 <= status < 300):
            snippet = (response.text or "")[:280]
            raise LLMError(f"HTTP {status}: {snippet}")
        raw_content = self._extract_content(response)
        try:
            return self._parse_json(raw_content)
        except ValueError:
            LOGGER.warning(
                "planner.llm invalid-json model=%s", resolved_model, exc_info=True
            )
            return {
                "type": "final",
                "answer": raw_content,
                "sources": [],
                "actions": ["raw"],
            }

    def _extract_content(self, response: requests.Response) -> str:
        try:
            payload = response.json()
        except ValueError as exc:
            raise LLMError("Non-JSON response from Ollama chat") from exc
        message = payload.get("message") if isinstance(payload, Mapping) else None
        if isinstance(message, Mapping):
            content = self._coerce_content(message.get("content"))
            if content:
                return content
        if isinstance(payload, Mapping):
            for key in ("response", "content"):
                content = self._coerce_content(payload.get(key))
                if content:
                    return content
        raise LLMError("Ollama chat response missing content")

    # ------------------------------------------------------------------
    # JSON coercion helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _coerce_content(raw: object) -> str | None:
        if isinstance(raw, str):
            cleaned = raw.strip()
            return cleaned or None
        if isinstance(raw, (Mapping, list, tuple)):
            try:
                return json.dumps(raw)
            except TypeError:
                try:
                    return json.dumps(raw, default=str)
                except TypeError as exc:  # pragma: no cover - defensive
                    raise LLMError("Unable to serialize Ollama content payload") from exc
        return None

    def _parse_json(self, text: str) -> Mapping[str, object]:
        cleaned = self._strip_code_fence(text)
        try:
            return json.loads(cleaned)
        except ValueError:
            snippet = self._extract_json_block(cleaned)
            return json.loads(snippet)

    @staticmethod
    def _strip_code_fence(text: str) -> str:
        stripped = text.strip()
        if stripped.startswith("```") and stripped.endswith("```"):
            lines = stripped.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            stripped = "\n".join(lines)
        return stripped.strip()

    @staticmethod
    def _extract_json_block(text: str) -> str:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("No JSON object found")
        candidate = text[start : end + 1]
        return candidate


__all__ = ["ChatMessage", "LLMError", "OllamaJSONClient"]
