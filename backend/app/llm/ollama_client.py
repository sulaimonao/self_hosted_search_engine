"""Hardened Ollama client used by self-heal planner flows."""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests

DEFAULT_OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
DEFAULT_MODEL = os.getenv("SELF_HEAL_MODEL", "gpt-oss")
DEFAULT_TIMEOUT = float(os.getenv("SELF_HEAL_TIMEOUT_S", "4"))
DEFAULT_TRIES = int(os.getenv("SELF_HEAL_TRIES", "1"))
ALLOWED_PREFIXES = ("gemma3:", "gpt-oss:")

_JSON_EXTRACT = re.compile(r"\{.*\}", re.S)


class OllamaClientError(RuntimeError):
    """Raised when the Ollama API cannot be reached or returns invalid JSON."""


@dataclass(slots=True)
class OllamaResponse:
    """Container for the parsed assistant payload."""

    content: str
    raw: Dict[str, Any]


class OllamaClient:
    """Lightweight HTTP wrapper around the Ollama REST API."""

    _model_cache = {"name": None, "ts": 0.0}

    def __init__(self, base_url: str | None = None) -> None:
        base = (base_url or DEFAULT_OLLAMA_HOST).rstrip("/")
        self.base_url = base or "http://127.0.0.1:11434"

    def resolve_model(self, preferred: str | None = None) -> str:
        """
        Return the first allowed model currently available.

        Restrict selection to gemma3:* or gpt-oss:* families and cache lookups
        briefly to avoid repeated /api/tags calls while the planner is busy.
        """
        now = time.time()
        cached = self._model_cache
        if cached["name"] and (now - cached["ts"]) < 60:
            return cached["name"]  # reuse healthy model discovered recently

        tags = self.health()
        models_raw = tags.get("models", []) if isinstance(tags, dict) else []

        models: list[str] = []
        for item in models_raw:
            if isinstance(item, dict):
                name = item.get("name")
                if isinstance(name, str) and name:
                    models.append(name)
            elif isinstance(item, str):
                models.append(item)

        if preferred:
            for candidate in models:
                if candidate == preferred or candidate.startswith(preferred):
                    cached.update({"name": candidate, "ts": now})
                    return candidate

        for prefix in ALLOWED_PREFIXES:
            for candidate in models:
                if candidate.startswith(prefix):
                    cached.update({"name": candidate, "ts": now})
                    return candidate

        raise RuntimeError("No allowed Ollama model available (need gemma3:* or gpt-oss:*)")

    # ------------------------------------------------------------------
    # Low-level helpers
    def _request(self, method: str, path: str, *, timeout: float) -> requests.Response:
        url = f"{self.base_url}{path}"
        try:
            response = requests.request(method, url, timeout=timeout)
        except requests.RequestException as exc:  # pragma: no cover - network issues
            raise OllamaClientError(f"ollama {method} {url} failed: {exc}") from exc
        if response.status_code >= 400:
            raise OllamaClientError(
                f"ollama {method} {url} returned {response.status_code}: {response.text[:200]}"
            )
        return response

    def _chat(self, payload: Dict[str, Any], *, timeout: float) -> OllamaResponse:
        url = f"{self.base_url}/api/chat"
        try:
            response = requests.post(url, json=payload, timeout=timeout)
        except requests.RequestException as exc:  # pragma: no cover - network issues
            raise OllamaClientError(f"ollama chat request failed: {exc}") from exc
        if response.status_code >= 400:
            raise OllamaClientError(
                f"ollama chat returned {response.status_code}: {response.text[:200]}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise OllamaClientError("ollama chat returned invalid JSON response") from exc
        message = payload.get("message") or {}
        content = message.get("content")
        if not isinstance(content, str) or not content:
            raise OllamaClientError("ollama chat returned empty message content")
        return OllamaResponse(content=content, raw=payload)

    # ------------------------------------------------------------------
    # Public API
    def health(self, *, timeout: float | None = None) -> Dict[str, Any]:
        """Return metadata about installed models by querying /api/tags."""

        effective_timeout = timeout if timeout is not None else DEFAULT_TIMEOUT
        response = self._request("GET", "/api/tags", timeout=effective_timeout)
        try:
            return response.json()
        except ValueError as exc:
            raise OllamaClientError("ollama tags response was not JSON") from exc

    def chat_json(
        self,
        system: str,
        user: str,
        *,
        model: str | None = None,
        timeout: float | None = None,
        tries: int | None = None,
    ) -> Dict[str, Any]:
        """Invoke /api/chat enforcing deterministic JSON responses."""

        model_name = model or DEFAULT_MODEL
        effective_timeout = timeout if timeout is not None else DEFAULT_TIMEOUT
        remaining = max(1, tries if tries is not None else DEFAULT_TRIES)
        system_base = system.strip()
        strict_prefix = (
            "Return ONLY VALID minified JSON. No commentary, markdown, or explanations. "
            "If you cannot comply respond with {}.\n"
        )
        last_error: Optional[Exception] = None

        for attempt in range(1, remaining + 1):
            prompt_system = system_base if attempt == 1 else f"{strict_prefix}{system_base}"
            payload = {
                "model": model_name,
                "stream": False,
                "format": "json",
                "messages": [
                    {"role": "system", "content": prompt_system},
                    {"role": "user", "content": user},
                ],
                "options": {
                    "temperature": 0.0,
                },
            }
            try:
                response = self._chat(payload, timeout=effective_timeout)
                content = response.content.strip()
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    match = _JSON_EXTRACT.search(content)
                    if match:
                        try:
                            return json.loads(match.group(0))
                        except json.JSONDecodeError as exc:
                            last_error = exc
                    else:
                        last_error = ValueError("no JSON object found in Ollama response")
            except Exception as exc:  # pragma: no cover - network issues / parse errors
                last_error = exc
            time.sleep(min(0.2 * attempt, 1.0))

        raise OllamaClientError(f"ollama chat_json failed after {remaining} attempt(s): {last_error}")


__all__ = [
    "DEFAULT_MODEL",
    "DEFAULT_OLLAMA_HOST",
    "DEFAULT_TIMEOUT",
    "DEFAULT_TRIES",
    "OllamaClient",
    "OllamaClientError",
]
