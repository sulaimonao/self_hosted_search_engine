"""Ship-It search history endpoints."""

from __future__ import annotations

import threading
from collections import deque
from datetime import datetime, timezone
from typing import Any

from flask import Blueprint, current_app, jsonify, request

bp = Blueprint("shipit_history", __name__, url_prefix="/api")


def _history_store() -> tuple[deque[dict[str, Any]], threading.Lock]:
    store = current_app.config.setdefault("SHIPIT_HISTORY", deque(maxlen=100))
    lock = current_app.config.get("SHIPIT_HISTORY_LOCK")
    if lock is None:
        lock = threading.Lock()
        current_app.config["SHIPIT_HISTORY_LOCK"] = lock
    return store, lock


@bp.get("/history")
def get_history() -> Any:
    limit_raw = request.args.get("limit")
    try:
        limit = int(limit_raw) if limit_raw is not None else 50
    except (TypeError, ValueError):
        limit = 50
    limit = max(1, min(limit, 200))

    store, lock = _history_store()
    with lock:
        items = list(store)
    payload = {
        "ok": True,
        "data": items[-limit:][::-1],
    }
    return jsonify(payload)


def append_history(entry: dict[str, Any]) -> None:
    store, lock = _history_store()
    enriched = {
        "id": entry.get("id"),
        "ts": entry.get("ts")
        or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "query": entry.get("query", ""),
        "filters": entry.get("filters"),
        "results_count": entry.get("results_count", 0),
    }
    with lock:
        store.append(enriched)


__all__ = ["bp", "get_history", "append_history"]
