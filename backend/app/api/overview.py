"""Data overview endpoint for the home dashboard."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

from flask import Blueprint, current_app, jsonify

from backend.app.config import AppConfig
from backend.app.db import AppStateDB

bp = Blueprint("overview_api", __name__, url_prefix="/api")


def _state_db() -> AppStateDB:
    state_db = current_app.config.get("APP_STATE_DB")
    if not isinstance(state_db, AppStateDB):  # pragma: no cover - misconfiguration
        raise RuntimeError("app state database unavailable")
    return state_db


def _app_config() -> AppConfig | None:
    config = current_app.config.get("APP_CONFIG")
    if isinstance(config, AppConfig):
        return config
    return None


_STORAGE_CACHE_LOCK = threading.Lock()
_STORAGE_CACHE_TTL = 300.0  # seconds
_STORAGE_CACHE: dict[str, Any] = {"signature": None, "timestamp": 0.0, "data": {}}


def _dir_size(path: Path) -> int:
    try:
        target = path.resolve()
    except OSError:
        target = path
    if not target.exists():
        return 0
    total = 0
    stack: list[Path] = [target]
    seen: set[Path] = set()
    while stack:
        current = stack.pop()
        try:
            resolved = current.resolve()
        except OSError:
            resolved = current
        if resolved in seen:
            continue
        seen.add(resolved)
        try:
            if resolved.is_symlink():
                continue
            if resolved.is_file():
                total += resolved.stat().st_size
                continue
            for child in resolved.iterdir():
                stack.append(child)
        except OSError:
            continue
    return total


def _storage_signature(targets: dict[str, Path]) -> tuple[tuple[str, str], ...]:
    signature = []
    for label, path in targets.items():
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        signature.append((label, str(resolved)))
    return tuple(sorted(signature))


def _storage_summary(targets: dict[str, Path]) -> dict[str, dict[str, str | int]]:
    signature = _storage_signature(targets)
    now = time.time()
    with _STORAGE_CACHE_LOCK:
        cached_sig = _STORAGE_CACHE.get("signature")
        cached_ts = float(_STORAGE_CACHE.get("timestamp") or 0.0)
        cached_data = _STORAGE_CACHE.get("data")
        if (
            cached_sig == signature
            and isinstance(cached_data, dict)
            and now - cached_ts <= _STORAGE_CACHE_TTL
        ):
            return dict(cached_data)
    storage_summary: dict[str, dict[str, str | int]] = {}
    seen_paths: set[Path] = set()
    for label, path in targets.items():
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        if resolved in seen_paths:
            continue
        seen_paths.add(resolved)
        storage_summary[label] = {"path": str(path), "bytes": _dir_size(path)}
    with _STORAGE_CACHE_LOCK:
        _STORAGE_CACHE.update(
            {"signature": signature, "timestamp": now, "data": dict(storage_summary)}
        )
    return storage_summary


@bp.get("/overview")
def overview_snapshot():
    state_db = _state_db()
    counters = state_db.overview_counters()
    config = _app_config()
    storage_targets: dict[str, Path] = {}
    if config is not None:
        storage_targets = {
            "data": config.app_state_db_path.parent,
            "index": config.index_dir,
            "agent": config.agent_data_dir,
            "logs": config.logs_dir,
        }
    else:  # Fallback to repo-relative data directory
        storage_targets = {
            "data": (Path(current_app.root_path).parents[1] / "data").resolve(),
        }
    counters["storage"] = _storage_summary(storage_targets)
    payload = {"ok": True, "data": counters}
    payload.update(counters)
    return jsonify(payload)


__all__ = ["bp"]
