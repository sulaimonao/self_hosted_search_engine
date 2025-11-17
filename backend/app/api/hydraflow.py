"""HydraFlow-style memory, thread, and task APIs."""

from __future__ import annotations

from typing import Any
from flask import Blueprint, current_app, jsonify, request

from backend.app.db import AppStateDB

bp = Blueprint("hydraflow_api", __name__, url_prefix="/api")


def _state_db() -> AppStateDB:
    state_db = current_app.config.get("APP_STATE_DB")
    if not isinstance(state_db, AppStateDB):  # pragma: no cover - misconfiguration
        raise RuntimeError("app state database unavailable")
    return state_db


def _as_mapping(payload: Any) -> dict[str, Any] | None:
    if isinstance(payload, dict):
        return payload
    return None


@bp.get("/threads")
def list_threads():
    limit = request.args.get("limit", type=int) or 50
    offset = request.args.get("offset", type=int) or 0
    state_db = _state_db()
    items = state_db.list_llm_threads(limit=limit, offset=offset)
    return jsonify({"items": items})


@bp.post("/threads")
def create_thread():
    payload = request.get_json(silent=True) or {}
    title = str(payload.get("title") or "").strip() or None
    description = str(payload.get("description") or "").strip() or None
    origin = str(payload.get("origin") or "").strip() or None
    metadata = _as_mapping(payload.get("metadata"))
    thread_id = str(payload.get("id") or "").strip() or None
    state_db = _state_db()
    if thread_id:
        state_db.ensure_llm_thread(
            thread_id,
            title=title,
            description=description,
            origin=origin,
            metadata=metadata,
        )
    else:
        thread_id = state_db.create_llm_thread(
            title=title,
            description=description,
            origin=origin,
            metadata=metadata,
        )
    record = state_db.get_llm_thread(thread_id)
    return jsonify({"id": thread_id, "thread": record}), 201


@bp.get("/threads/<thread_id>")
def get_thread(thread_id: str):
    state_db = _state_db()
    record = state_db.get_llm_thread(thread_id)
    if not record:
        return jsonify({"error": "not_found"}), 404
    return jsonify({"thread": record})


@bp.delete("/threads/<thread_id>")
def delete_thread(thread_id: str):
    state_db = _state_db()
    stats = state_db.delete_llm_thread(thread_id)
    if stats["threads"] == 0:
        return jsonify({"error": "not_found"}), 404
    return jsonify({"deleted": thread_id, "stats": stats})


@bp.get("/threads/<thread_id>/messages")
def list_thread_messages(thread_id: str):
    limit = request.args.get("limit", type=int) or 50
    state_db = _state_db()
    items = state_db.list_llm_messages(thread_id, limit=limit, ascending=True)
    return jsonify({"items": items})


@bp.post("/threads/<thread_id>/messages")
def create_thread_message(thread_id: str):
    payload = request.get_json(silent=True) or {}
    content = str(payload.get("content") or "").strip()
    if not content:
        return jsonify({"error": "content_required"}), 400
    role = str(payload.get("role") or "user").strip().lower() or "user"
    if role not in {"user", "assistant", "system", "tool"}:
        return jsonify({"error": "invalid_role"}), 400
    metadata = _as_mapping(payload.get("metadata"))
    parent_id = str(payload.get("parent_id") or "").strip() or None
    message_id = str(payload.get("id") or "").strip() or None
    tokens_raw = payload.get("tokens")
    tokens: int | None = None
    if tokens_raw is not None:
        try:
            tokens = int(tokens_raw)
        except (TypeError, ValueError):
            tokens = None
    state_db = _state_db()
    stored_id = state_db.append_llm_message(
        thread_id=thread_id,
        role=role,
        content=content,
        message_id=message_id,
        parent_id=parent_id,
        tokens=tokens,
        metadata=metadata,
    )
    return jsonify({"id": stored_id}), 201


@bp.post("/tasks")
def create_task():
    payload = request.get_json(silent=True) or {}
    title = str(payload.get("title") or "").strip()
    if not title:
        return jsonify({"error": "title_required"}), 400
    thread_id = str(payload.get("thread_id") or "").strip() or None
    description = str(payload.get("description") or "").strip() or None
    status = str(payload.get("status") or "pending").strip() or "pending"
    priority_raw = payload.get("priority")
    try:
        priority = int(priority_raw) if priority_raw is not None else 0
    except (TypeError, ValueError):
        priority = 0
    due_at = str(payload.get("due_at") or "").strip() or None
    owner = str(payload.get("owner") or "").strip() or None
    metadata = _as_mapping(payload.get("metadata"))
    result = _as_mapping(payload.get("result"))
    state_db = _state_db()
    task_id = state_db.create_task(
        title=title,
        description=description,
        thread_id=thread_id,
        status=status,
        priority=priority,
        due_at=due_at,
        owner=owner,
        metadata=metadata,
        result=result,
    )
    record = state_db.get_task(task_id)
    return jsonify({"id": task_id, "task": record}), 201


@bp.get("/tasks")
def list_tasks():
    status = request.args.get("status") or None
    thread_id = request.args.get("thread_id") or None
    limit = request.args.get("limit", type=int) or 50
    state_db = _state_db()
    items = state_db.list_tasks(status=status, thread_id=thread_id, limit=limit)
    return jsonify({"items": items})


@bp.get("/tasks/<task_id>")
def get_task(task_id: str):
    state_db = _state_db()
    record = state_db.get_task(task_id)
    if not record:
        return jsonify({"error": "not_found"}), 404
    return jsonify({"task": record})


@bp.patch("/tasks/<task_id>")
def update_task(task_id: str):
    payload = request.get_json(silent=True) or {}
    metadata = _as_mapping(payload.get("metadata")) if "metadata" in payload else None
    result = _as_mapping(payload.get("result")) if "result" in payload else None
    kwargs: dict[str, Any] = {
        "title": str(payload.get("title") or "").strip() or None,
        "description": str(payload.get("description") or "").strip() or None,
        "status": str(payload.get("status") or "").strip() or None,
        "due_at": str(payload.get("due_at") or "").strip() or None,
        "owner": str(payload.get("owner") or "").strip() or None,
        "thread_id": str(payload.get("thread_id") or "").strip() or None,
        "closed_at": str(payload.get("closed_at") or "").strip() or None,
    }
    if metadata is not None:
        kwargs["metadata"] = metadata
    if result is not None:
        kwargs["result"] = result
    if "priority" in payload:
        try:
            kwargs["priority"] = int(payload.get("priority"))
        except (TypeError, ValueError):
            kwargs["priority"] = None
    state_db = _state_db()
    record = state_db.update_task(task_id, **kwargs)
    if not record:
        return jsonify({"error": "not_found"}), 404
    return jsonify({"task": record})


@bp.post("/tasks/<task_id>/events")
def create_task_event(task_id: str):
    payload = request.get_json(silent=True) or {}
    event_type = str(payload.get("event_type") or "").strip()
    if not event_type:
        return jsonify({"error": "event_type_required"}), 400
    metadata = _as_mapping(payload.get("payload"))
    state_db = _state_db()
    event_id = state_db.record_task_event(
        task_id,
        event_type=event_type,
        payload=metadata,
    )
    return jsonify({"id": event_id}), 201


@bp.get("/tasks/<task_id>/events")
def list_task_events(task_id: str):
    limit = request.args.get("limit", type=int) or 100
    state_db = _state_db()
    events = state_db.list_task_events(task_id, limit=limit)
    return jsonify({"items": events})


@bp.post("/memories/upsert")
def upsert_memory():
    payload = request.get_json(silent=True) or {}
    memory_id = str(payload.get("id") or "").strip()
    scope = str(payload.get("scope") or "").strip()
    value = str(payload.get("value") or "").strip()
    if not memory_id or not scope or not value:
        return jsonify({"error": "id_scope_value_required"}), 400
    scope_ref = str(payload.get("scope_ref") or "").strip() or None
    key = str(payload.get("key") or "").strip() or None
    metadata = _as_mapping(payload.get("metadata"))
    strength_raw = payload.get("strength")
    try:
        strength = float(strength_raw) if strength_raw is not None else 1.0
    except (TypeError, ValueError):
        strength = 1.0
    strength = max(0.0, min(1.0, strength))
    thread_id = str(payload.get("thread_id") or "").strip() or None
    task_id = str(payload.get("task_id") or "").strip() or None
    source_message_id = str(payload.get("source_message_id") or "").strip() or None
    embedding_ref = str(payload.get("embedding_ref") or "").strip() or None
    state_db = _state_db()
    state_db.upsert_memory(
        memory_id=memory_id,
        scope=scope,
        scope_ref=scope_ref,
        key=key,
        value=value,
        metadata=metadata,
        strength=strength,
        thread_id=thread_id,
        task_id=task_id,
        source_message_id=source_message_id,
        embedding_ref=embedding_ref,
    )
    return jsonify({"ok": True})


@bp.post("/memories/search")
def search_memory():
    payload = request.get_json(silent=True) or {}
    query = str(payload.get("query") or "").strip() or None
    scope = str(payload.get("scope") or "").strip() or None
    scope_ref = str(payload.get("scope_ref") or "").strip() or None
    limit = payload.get("limit")
    try:
        limit_value = int(limit) if limit is not None else 20
    except (TypeError, ValueError):
        limit_value = 20
    state_db = _state_db()
    items = state_db.search_memories(
        query=query,
        scope=scope,
        scope_ref=scope_ref,
        limit=limit_value,
    )
    return jsonify({"items": items})


__all__ = ["bp"]
