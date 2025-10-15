"""Helpers for interacting with a local Ollama instance."""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Iterable, Mapping
from typing import Any

import requests
from flask import current_app

try:  # pragma: no cover - optional dependency during tests
    from backend.app import EMBEDDING_MODEL_PATTERNS
except Exception:  # pragma: no cover - defensive import fallback
    EMBEDDING_MODEL_PATTERNS = (
        re.compile(r"(?:^|[-_:])embed(?:ding)?", re.IGNORECASE),
        re.compile(r"(?:^|[-_:])gte[-_:]", re.IGNORECASE),
        re.compile(r"(?:^|[-_:])bge[-_:]", re.IGNORECASE),
        re.compile(r"(?:^|[-_:])text2vec", re.IGNORECASE),
        re.compile(r"(?:^|[-_:])e5[-_:]", re.IGNORECASE),
    )


DEFAULT_TIMEOUT = 5.0
_NON_CHAT_KEYWORDS = (
    "embed",
    "embedding",
    "-embed",
    "text-embedding",
    "vector",
)
_CHAT_DENYLIST = {
    "clip",
    "imagebind",
}


def _coerce_name(candidate: Any) -> str | None:
    if isinstance(candidate, str):
        text = candidate.strip()
        return text or None
    return None


def _unique(items: Iterable[str]) -> list[str]:
    seen: dict[str, None] = {}
    for item in items:
        if item not in seen:
            seen[item] = None
    return list(seen.keys())


def _looks_like_embedding(name: str) -> bool:
    if any(pattern.search(name) for pattern in EMBEDDING_MODEL_PATTERNS):
        return True
    lowered = name.lower()
    if any(keyword in lowered for keyword in _NON_CHAT_KEYWORDS):
        return True
    return False


def _looks_like_chat(name: str) -> bool:
    if name.lower() in _CHAT_DENYLIST:
        return False
    return not _looks_like_embedding(name)


def _resolve_base_url(explicit: str | None = None) -> str:
    if explicit:
        return explicit.rstrip("/")
    try:
        config = current_app.config.get("RAG_ENGINE_CONFIG")
        if config is not None:
            return str(config.ollama.base_url).rstrip("/")
    except RuntimeError:  # pragma: no cover - fallback when no app context
        pass
    return os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")


def list_models(
    *,
    base_url: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    chat_only: bool = False,
) -> list[str]:
    """Return model tags available on the Ollama instance.

    When ``chat_only`` is ``True`` embedding-oriented models are filtered out
    using both a regex deny-list and keyword heuristics.
    """

    resolved_base = _resolve_base_url(base_url)
    try:
        response = requests.get(f"{resolved_base}/api/tags", timeout=timeout)
        response.raise_for_status()
    except requests.RequestException:
        return []

    try:
        payload = response.json()
    except ValueError:
        return []

    models: list[str] = []
    raw_models = payload.get("models")
    if isinstance(raw_models, Iterable):
        for entry in raw_models:
            name: str | None = None
            if isinstance(entry, Mapping):
                name = (
                    _coerce_name(entry.get("name"))
                    or _coerce_name(entry.get("model"))
                    or _coerce_name(entry.get("tag"))
                )
            else:
                name = _coerce_name(entry)
            if name:
                models.append(name)

    models = _unique(models)
    if chat_only:
        models = [model for model in models if _looks_like_chat(model)]
    return models


def has_model(model: str, *, base_url: str | None = None) -> bool:
    if not model:
        return False
    available = list_models(base_url=base_url, chat_only=False)
    return model in available


def pull_model(
    model: str,
    *,
    base_url: str | None = None,
    env: Mapping[str, str] | None = None,
) -> subprocess.Popen[bytes]:
    """Spawn ``ollama pull <model>`` in a background subprocess.

    The process is kicked off asynchronously and the caller is responsible for
    monitoring progress when needed. ``OLLAMA_HOST`` is injected so the CLI
    targets the same host used by the HTTP helpers.
    """

    if not model:
        raise ValueError("model is required")
    resolved_base = _resolve_base_url(base_url)
    command = ["ollama", "pull", model]
    proc_env = os.environ.copy()
    proc_env.setdefault("OLLAMA_HOST", resolved_base)
    if env:
        proc_env.update({str(k): str(v) for k, v in env.items()})
    return subprocess.Popen(  # noqa: S603 - command is controlled
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=proc_env,
    )


def supports_vision(model: str) -> bool:
    """Best-effort heuristic for models that can accept images."""

    lowered = model.lower()
    return any(token in lowered for token in {"vision", "multimodal", "vl", "lmstudio"})


__all__ = [
    "list_models",
    "has_model",
    "pull_model",
    "supports_vision",
]
