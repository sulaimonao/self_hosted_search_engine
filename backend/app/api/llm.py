"""Endpoints exposing local Ollama model inventory and health."""

from __future__ import annotations

import shutil
import time
from collections.abc import Iterable, Mapping
from typing import Any, TYPE_CHECKING

import requests
from flask import Blueprint, current_app, g, jsonify

from .. import EMBEDDING_MODEL_PATTERNS
from server.json_logger import log_event

if TYPE_CHECKING:  # pragma: no cover - imports for type checkers only
    from backend.app.embedding_manager import EmbeddingManager
    from backend.app.config import AppConfig
    from engine.config import EngineConfig


bp = Blueprint("llm_api", __name__, url_prefix="/api/llm")


def _get_engine_config() -> "EngineConfig":
    config = current_app.config.get("RAG_ENGINE_CONFIG")
    if config is None:
        raise RuntimeError("RAG_ENGINE_CONFIG missing from app config")
    return config


def _get_app_config() -> "AppConfig":
    config = current_app.config.get("APP_CONFIG")
    if config is None:
        raise RuntimeError("APP_CONFIG missing from app config")
    return config


def _get_embed_manager() -> "EmbeddingManager | None":
    manager = current_app.config.get("RAG_EMBED_MANAGER")
    return manager  # type: ignore[return-value]


def _coerce_name(value: Any) -> str | None:
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return None


def _extract_models(payload: Mapping[str, Any]) -> list[str]:
    models_raw = payload.get("models")
    names: list[str] = []
    if isinstance(models_raw, Iterable):
        for entry in models_raw:
            if isinstance(entry, Mapping):
                candidate = entry.get("name") or entry.get("model") or entry.get("tag")
                name = _coerce_name(candidate)
            else:
                name = _coerce_name(entry)
            if name:
                names.append(name)
    return names


def _unique(items: Iterable[str]) -> list[str]:
    seen: dict[str, None] = {}
    for item in items:
        if item not in seen:
            seen[item] = None
    return list(seen.keys())


def _probe_ollama(base_url: str, manager: "EmbeddingManager | None") -> dict[str, Any]:
    """Collect model names and reachability information for Ollama."""

    start = time.perf_counter()
    reachable = False
    error: str | None = None
    http_models: list[str] = []
    try:
        response = requests.get(f"{base_url}/api/tags", timeout=3)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, Mapping):
            http_models = _extract_models(data)
        reachable = True
    except requests.RequestException as exc:
        error = str(exc)
    except ValueError:
        error = "invalid_json"
    duration_ms = int((time.perf_counter() - start) * 1000)

    cli_models: list[str] = []
    if manager is not None and not http_models:
        try:
            cli_models = list(manager.list_models())
        except Exception:  # pragma: no cover - subprocess/CLI failures are best effort
            current_app.logger.debug("Embedding manager list_models failed", exc_info=True)

    models = http_models or cli_models
    return {
        "reachable": reachable,
        "models": _unique(model for model in models if model),
        "duration_ms": duration_ms,
        "error": error,
    }


def _is_embedding_model(name: str) -> bool:
    return any(pattern.search(name) for pattern in EMBEDDING_MODEL_PATTERNS)


@bp.get("/models")
def llm_models() -> Any:
    engine_config = _get_engine_config()
    manager = _get_embed_manager()

    probe = _probe_ollama(engine_config.ollama.base_url, manager)
    available = probe["models"]
    configured = {
        "primary": _coerce_name(engine_config.models.llm_primary),
        "fallback": _coerce_name(engine_config.models.llm_fallback),
        "embedder": _coerce_name(engine_config.models.embed),
    }

    detailed_models = [
        {
            "name": model,
            "kind": "embedding" if _is_embedding_model(model) else "chat",
            "installed": model in available,
        }
        for model in _unique(
            [value for value in configured.values() if value]
            + available
        )
    ]

    trace_id = getattr(g, "trace_id", None)
    log_event(
        "INFO",
        "llm.models",
        trace=trace_id,
        available=len(available),
        configured_primary=configured["primary"],
        configured_fallback=configured["fallback"],
        configured_embedder=configured["embedder"],
    )

    payload = {
        "available": available,
        "configured": configured,
        "ollama_host": engine_config.ollama.base_url,
        "models": detailed_models,
    }
    if probe.get("error"):
        payload["error"] = probe["error"]
    return jsonify(payload)


@bp.get("/health")
def llm_health() -> Any:
    engine_config = _get_engine_config()
    manager = _get_embed_manager()
    probe = _probe_ollama(engine_config.ollama.base_url, manager)
    payload = {
        "reachable": bool(probe["reachable"]),
        "model_count": len(probe["models"]),
        "duration_ms": int(probe["duration_ms"]),
        "host": engine_config.ollama.base_url,
    }
    if probe.get("error"):
        payload["error"] = probe["error"]
    trace_id = getattr(g, "trace_id", None)
    log_event(
        "INFO",
        "llm.health",
        trace=trace_id,
        reachable=payload["reachable"],
        models=payload["model_count"],
    )
    return jsonify(payload)


@bp.get("/status")
def llm_status() -> Any:
    app_config = _get_app_config()
    engine_config = _get_engine_config()
    manager = _get_embed_manager()

    probe = _probe_ollama(engine_config.ollama.base_url, manager)
    reachable = bool(probe["reachable"])
    available = probe["models"]
    installed = shutil.which("ollama") is not None or reachable

    payload = {
        "installed": bool(installed),
        "running": bool(reachable),
        "host": engine_config.ollama.base_url or app_config.ollama_url,
        "models": available,
    }
    if probe.get("error"):
        payload["error"] = probe["error"]

    trace_id = getattr(g, "trace_id", None)
    log_event(
        "INFO",
        "llm.status",
        trace=trace_id,
        installed=payload["installed"],
        running=payload["running"],
        models=len(available),
    )
    return jsonify(payload)


__all__ = ["bp"]
