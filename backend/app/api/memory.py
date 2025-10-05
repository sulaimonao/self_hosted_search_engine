"""Memory CRUD endpoints."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from backend.app.db import AppStateDB

bp = Blueprint("memory_api", __name__, url_prefix="/api")


@bp.post("/memory")
def upsert_memory():
    payload = request.get_json(force=True, silent=True) or {}
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
