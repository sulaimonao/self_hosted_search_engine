"""Memory CRUD endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
import threading
from typing import Any
from uuid import uuid4

from flask import Blueprint, current_app, jsonify, request

from backend.app.db import AppStateDB

bp = Blueprint("memory_api", __name__, url_prefix="/api")


def _shipit_memory_store() -> tuple[list[dict[str, Any]], threading.Lock]:
    store = current_app.config.setdefault("SHIPIT_MEMORY", [])
    lock = current_app.config.get("SHIPIT_MEMORY_LOCK")
    if lock is None:
        lock = threading.Lock()
        current_app.config["SHIPIT_MEMORY_LOCK"] = lock
    return store, lock


@bp.post("/memory")
def upsert_memory():
    payload = request.get_json(force=True, silent=True) or {}
    if "key" in payload and "value" in payload:
        key = payload.get("key")
        if not isinstance(key, str) or not key.strip():
            return jsonify({"ok": False, "error": "key_required"}), 400
        value = payload.get("value")
        ttl_raw = payload.get("ttl_s")
        ttl_s: float | None = None
        if ttl_raw is not None:
            try:
                ttl_s = max(0.0, float(ttl_raw))
            except (TypeError, ValueError):
                return jsonify({"ok": False, "error": "invalid_ttl"}), 400
        tags_raw = payload.get("tags")
        tags: list[str] | None
        if tags_raw is None:
            tags = None
        elif isinstance(tags_raw, list) and all(
            isinstance(tag, str) for tag in tags_raw
        ):
            tags = [tag for tag in tags_raw if tag]
        else:
            return jsonify({"ok": False, "error": "invalid_tags"}), 400
        entry = {
            "id": uuid4().hex,
            "key": key.strip(),
            "value": value,
            "ttl_s": ttl_s,
            "tags": tags or [],
            "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        store, lock = _shipit_memory_store()
        with lock:
            store.append(entry)
        return jsonify({"ok": True}), 201
    memory_id = str(payload.get("id") or "").strip() or None
    scope = str(payload.get("scope") or "").strip() or None
    if not memory_id or not scope:
        return jsonify({"error": "id_and_scope_required"}), 400
    scope_ref = payload.get("scope_ref")
    key = payload.get("key")
    value = str(payload.get("value") or "").strip()
    if not value:
        return jsonify({"error": "value_required"}), 400
    metadata = payload.get("metadata") or {}
    try:
        strength = float(payload.get("strength", 1.0))
    except (TypeError, ValueError):
        strength = 1.0
    strength = max(0.0, min(1.0, strength))

    state_db: AppStateDB = current_app.config["APP_STATE_DB"]
    state_db.upsert_memory(
        memory_id=memory_id,
        scope=scope,
        scope_ref=scope_ref,
        key=key,
        value=value,
        metadata=metadata,
        strength=strength,
    )
    return jsonify({"ok": True})


@bp.get("/memory")
def list_memory():
    scope = request.args.get("scope", "").strip()
    if not scope:
        return jsonify({"error": "scope_required"}), 400
    scope_ref = request.args.get("ref")
    state_db: AppStateDB = current_app.config["APP_STATE_DB"]
    items = state_db.list_memories(scope=scope, scope_ref=scope_ref, limit=50)
    return jsonify({"items": items})


__all__ = ["bp", "upsert_memory", "list_memory"]
