"""Helpers for assembling runtime health and capability snapshots."""

from __future__ import annotations

import logging
import shutil
import socket
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from flask import current_app

from backend.app.api.llm import ALIAS_MAP
from backend.app.config.store import read_config
from backend.app.routes.util import get_db
from backend.app.services import index_health
from backend.app.services import ollama_client
from server.refresh_worker import RefreshWorker
from backend.app.db import AppStateDB


LOGGER = logging.getLogger(__name__)


REQUIRED_CHAT_FAMILIES = ("gemma-3", "gpt-oss")
REQUIRED_EMBED_MODEL = "embeddinggemma"


@dataclass(slots=True)
class HealthComponent:
    name: str
    status: str
    detail: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "status": self.status, "detail": self.detail}


def _normalise_family(name: str) -> str:
    base = name.split(":", 1)[0].strip()
    if not base:
        return ""
    key = "".join(ch for ch in base.lower() if ch.isalnum())
    for canonical, aliases in ALIAS_MAP.items():
        canonical_key = "".join(ch for ch in canonical.lower() if ch.isalnum())
        if key == canonical_key:
            return canonical
        if any(
            key == "".join(ch for ch in alias.lower() if ch.isalnum())
            for alias in aliases
        ):
            return canonical
    return base.lower()


def _port_open(host: str, port: int, timeout: float = 0.25) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _llm_health() -> HealthComponent:
    engine_config = current_app.config.get("RAG_ENGINE_CONFIG")
    base_url = getattr(getattr(engine_config, "ollama", None), "base_url", None)
    available = ollama_client.list_models(base_url=base_url, chat_only=False)
    chat_models = ollama_client.list_models(base_url=base_url, chat_only=True)
    chat_families = {_normalise_family(model) for model in chat_models}
    missing = [
        family for family in REQUIRED_CHAT_FAMILIES if family not in chat_families
    ]
    embedding_available = any(
        _normalise_family(model) == REQUIRED_EMBED_MODEL for model in available
    )
    installed_cli = shutil.which("ollama") is not None
    status = "ok"
    if missing or not embedding_available:
        status = "degraded"
    if not chat_models and not available:
        status = "error"
    detail = {
        "base_url": getattr(getattr(engine_config, "ollama", None), "base_url", None),
        "available": sorted(available),
        "chat": sorted(chat_models),
        "missing_families": missing,
        "embedding_available": embedding_available,
        "ollama_cli": installed_cli,
    }
    return HealthComponent("llm", status, detail)


def _index_health() -> HealthComponent:
    payload = index_health.probe_all()
    status = str(payload.get("status") or "unknown")
    detail = {
        "stores": payload.get("stores", []),
        "last_reindex": payload.get("last_reindex"),
        "rebuild_available": bool(payload.get("rebuild_available")),
    }
    return HealthComponent("index", status, detail)


def _crawler_health() -> HealthComponent:
    worker = current_app.config.get("REFRESH_WORKER")
    if not isinstance(worker, RefreshWorker):
        state_db = current_app.config.get("APP_STATE_DB")
        overview = {}
        status = "unknown"
        if isinstance(state_db, AppStateDB):
            try:
                overview = state_db.crawl_overview()
                queued = int(overview.get("queued") or 0)
                running = int(overview.get("running") or 0)
                status = "running" if running else ("idle" if queued == 0 else "queued")
            except Exception:  # pragma: no cover - defensive guard
                overview = {}
                status = "unknown"
        return HealthComponent("crawler", status, {"available": False, "overview": overview})
    snapshot = worker.status()
    active = snapshot.get("active") or []
    recent = snapshot.get("recent") or []
    has_error = any(job.get("state") == "error" for job in active)
    has_running = any(job.get("state") == "running" for job in active)
    status = "idle"
    if has_running:
        status = "running"
    if has_error:
        status = "degraded"
    detail = {
        "active": active,
        "recent": recent,
    }
    return HealthComponent("crawler", status, detail)


def _desktop_health() -> HealthComponent:
    bridge_state = current_app.config.get("DESKTOP_BRIDGE_STATE")
    if isinstance(bridge_state, Mapping):
        detail = dict(bridge_state)
    else:
        detail = {"bridge": bool(bridge_state)}
    status = "ok" if detail.get("bridge") else "unknown"
    return HealthComponent("desktop", status, detail)


def build_health_snapshot() -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    components = [
        _llm_health(),
        _index_health(),
        _crawler_health(),
        _desktop_health(),
    ]
    worst = "ok"
    for component in components:
        status = component.status
        if status == "error":
            worst = "error"
            break
        if status == "degraded" and worst == "ok":
            worst = "degraded"
    environment = {
        "python": sys.version.split(" ")[0],
        "node": shutil.which("node") is not None,
        "ollama": shutil.which("ollama") is not None,
    }
    backend_port = int(current_app.config.get("PORT", 5050))
    environment["api_port_open"] = _port_open("127.0.0.1", backend_port)
    payload = {
        "timestamp": now.isoformat(timespec="seconds"),
        "status": worst,
        "components": {component.name: component.to_dict() for component in components},
        "environment": environment,
    }
    return payload


def build_capability_snapshot() -> dict[str, Any]:
    app = current_app
    vector_service = app.config.get("VECTOR_INDEX_SERVICE")
    search_service = app.config.get("SEARCH_SERVICE")
    shadow_manager = app.config.get("SHADOW_INDEX_MANAGER")

    vector_status = None
    if vector_service is not None and hasattr(vector_service, "embedding_status"):
        try:
            vector_status = vector_service.embedding_status()
        except Exception:  # pragma: no cover - defensive guard
            vector_status = None

    all_models, chat_models = _list_models()
    llm_health = bool(all_models or chat_models)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "llm": {
            "health": llm_health,
            "chat": bool(chat_models),
            "models": chat_models,
        },
        "search": {
            "bm25": search_service is not None,
            "vector": bool(vector_status and vector_status.get("ready")),
            "hybrid": bool(
                vector_status and vector_status.get("ready") and search_service
            ),
            "embedding": vector_status or {},
        },
        "shadow": {
            "config": bool(shadow_manager and hasattr(shadow_manager, "get_config")),
            "toggle": bool(shadow_manager and hasattr(shadow_manager, "toggle")),
        },
        "discovery": {
            "events_stream": bool(app.config.get("FEATURE_LOCAL_DISCOVERY")),
        },
    }


def _list_models() -> tuple[list[str], list[str]]:
    engine_config = current_app.config.get("RAG_ENGINE_CONFIG")
    if engine_config is None:
        return [], []
    base_url = getattr(engine_config.ollama, "base_url", None)
    all_models = ollama_client.list_models(base_url=base_url, chat_only=False)
    chat_models = ollama_client.list_models(base_url=base_url, chat_only=True)
    return all_models, chat_models


def diagnostics_snapshot() -> dict[str, Any]:
    health = build_health_snapshot()
    capabilities = build_capability_snapshot()
    config: dict[str, Any] = {}
    try:
        with get_db() as conn:
            config = read_config(conn).model_dump()
    except Exception:  # pragma: no cover - diagnostics best-effort
        LOGGER.debug("failed to capture config snapshot", exc_info=True)
    return {
        "captured_at": time.time(),
        "health": health,
        "capabilities": capabilities,
        "config": config,
        "links": {
            "ui_to_api": True,
            "api_to_llm": health["components"]["llm"]["status"] != "error",
            "crawler_to_index": health["components"]["index"]["status"] != "error",
            "desktop_bridge": health["components"].get("desktop", {}).get("status")
            == "ok",
        },
    }


def run_repairs() -> dict[str, Any]:
    results: dict[str, Any] = {"actions": []}
    vector_service = current_app.config.get("VECTOR_INDEX_SERVICE")
    if vector_service is not None and hasattr(vector_service, "warmup"):
        try:
            vector_service.warmup(attempts=1)
            results["actions"].append({"name": "vector_warmup", "ok": True})
        except Exception as exc:  # pragma: no cover - defensive guard
            results.setdefault("errors", []).append(str(exc))
            results["actions"].append(
                {"name": "vector_warmup", "ok": False, "error": str(exc)}
            )
    try:
        rebuild = index_health.rebuild()
        results["actions"].append(
            {"name": "index_rebuild", "ok": bool(rebuild.get("accepted"))}
        )
    except Exception as exc:  # pragma: no cover
        results.setdefault("errors", []).append(str(exc))
        results["actions"].append(
            {"name": "index_rebuild", "ok": False, "error": str(exc)}
        )
    return results


__all__ = [
    "build_health_snapshot",
    "build_capability_snapshot",
    "diagnostics_snapshot",
    "run_repairs",
]
