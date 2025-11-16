"""Data overview endpoint for the home dashboard."""

from __future__ import annotations

from pathlib import Path

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
    storage_summary: dict[str, dict[str, str | int]] = {}
    seen_paths: set[Path] = set()
    for label, path in storage_targets.items():
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        if resolved in seen_paths:
            continue
        seen_paths.add(resolved)
        storage_summary[label] = {"path": str(path), "bytes": _dir_size(path)}
    counters["storage"] = storage_summary
    return jsonify(counters)


__all__ = ["bp"]
