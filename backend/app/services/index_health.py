"""Inspection utilities for index health monitoring."""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

import duckdb
from flask import current_app
from whoosh import index as whoosh_index


LOGGER = logging.getLogger(__name__)


def _count_sqlite(path: Path, table: str) -> int | None:
    if not path.exists():
        return None
    try:
        conn = sqlite3.connect(path)
        try:
            row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        finally:
            conn.close()
        return int(row[0]) if row and row[0] is not None else 0
    except sqlite3.Error:
        LOGGER.debug("sqlite count failed for %s", path, exc_info=True)
        return None


def _count_duckdb(path: Path) -> int | None:
    if not path.exists():
        return None
    try:
        with duckdb.connect(str(path)) as conn:
            row = conn.execute("SELECT COUNT(*) FROM documents").fetchone()
        return int(row[0]) if row and row[0] is not None else 0
    except duckdb.Error:
        LOGGER.debug("duckdb count failed for %s", path, exc_info=True)
        return None


def _count_whoosh(index_dir: Path) -> int | None:
    if not index_dir.exists():
        return None
    try:
        ix = whoosh_index.open_dir(index_dir)
    except Exception:
        LOGGER.debug("unable to open whoosh index at %s", index_dir, exc_info=True)
        return None
    try:
        return ix.doc_count()
    finally:
        try:
            ix.close()
        except Exception:
            pass


def _timestamp(path: Path) -> float | None:
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def probe_all() -> dict[str, Any]:
    app = current_app
    config = app.config.get("APP_CONFIG")
    stores: list[dict[str, Any]] = []

    if config is None:
        return {"stores": [], "status": "red", "rebuild_available": False}

    app_state_path = Path(config.app_state_db_path)
    app_state_count = _count_sqlite(app_state_path, "documents")
    stores.append(
        {
            "name": "app_state",
            "count": app_state_count if app_state_count is not None else 0,
            "ok": app_state_count is not None,
            "path": str(app_state_path),
        }
    )

    vector_service = app.config.get("VECTOR_INDEX_SERVICE")
    vector_ok = False
    vector_count = 0
    vector_dims = None
    if vector_service is not None:
        try:
            metadata = vector_service.metadata()
            vector_count = int(metadata.get("documents") or 0)
            vector_dims = metadata.get("dimensions")
            vector_ok = True
        except Exception:
            LOGGER.debug("vector metadata probe failed", exc_info=True)
    stores.append(
        {
            "name": "vector_index",
            "count": vector_count,
            "dimensions": vector_dims,
            "ok": vector_ok,
        }
    )

    duck_count = _count_duckdb(Path(config.agent_data_dir) / "vector" / "vectors.duckdb")
    stores.append(
        {
            "name": "vector_duckdb",
            "count": duck_count if duck_count is not None else 0,
            "ok": duck_count is not None,
        }
    )

    whoosh_count = _count_whoosh(Path(config.index_dir))
    stores.append(
        {
            "name": "keyword_index",
            "count": whoosh_count if whoosh_count is not None else 0,
            "ok": whoosh_count is not None,
        }
    )

    ok_states = [entry.get("ok") for entry in stores]
    if ok_states and all(ok_states):
        status = "green"
    elif any(ok_states):
        status = "yellow"
    else:
        status = "red"

    last_reindex = _timestamp(Path(config.last_index_time_path))
    return {
        "stores": stores,
        "last_reindex": last_reindex,
        "status": status,
        "rebuild_available": True,
    }


def rebuild(store: str | None = None) -> dict[str, Any]:
    app = current_app
    config = app.config.get("APP_CONFIG")
    vector_service = app.config.get("VECTOR_INDEX_SERVICE")
    search_service = app.config.get("SEARCH_SERVICE")

    if config is None:
        return {"accepted": False, "reason": "config_unavailable"}

    def _task() -> None:
        try:
            if search_service is not None:
                search_service.reload_index()
        except Exception:
            LOGGER.exception("keyword index reload failed")
        try:
            if vector_service is not None:
                vector_service.warmup(attempts=1)
        except Exception:
            LOGGER.exception("vector index warmup failed")
        try:
            marker = Path(config.last_index_time_path)
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(str(int(time.time())) + "\n", encoding="utf-8")
        except Exception:
            LOGGER.exception("failed to update index timestamp")

    threading.Thread(target=_task, name="index-rebuild", daemon=True).start()
    return {"accepted": True, "store": store or "all"}


__all__ = ["probe_all", "rebuild"]
