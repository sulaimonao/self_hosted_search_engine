"""Chat persistence endpoints."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from backend.app.db import AppStateDB
from backend.app.services.context_assembler import assemble_context

bp = Blueprint("chat_history_api", __name__, url_prefix="/api")


def _normalize_role(role: str | None) -> str:
    allowed = {"user", "assistant", "system"}
    normalized = (role or "").strip().lower()
    return normalized if normalized in allowed else "user"


@bp.post("/chat/<thread_id>/message")
def store_chat_message(thread_id: str):
    payload = request.get_json(force=True, silent=True) or {}
    content = str(payload.get("content") or "").strip()
    if not content:
        return jsonify({"error": "content_required"}), 400
    role = _normalize_role(payload.get("role"))
    message_id = str(payload.get("id") or "").strip() or None
    tokens = payload.get("tokens")
    try:
        tokens_value = int(tokens) if tokens is not None else None
    except (TypeError, ValueError):
        tokens_value = None
    state_db: AppStateDB = current_app.config["APP_STATE_DB"]
    state_db.upsert_thread(thread_id)
    stored_id = state_db.add_chat_message(
        message_id=message_id,
        thread_id=thread_id,
        role=role,
        content=content,
        tokens=tokens_value,
    )
    return jsonify({"ok": True, "id": stored_id})


@bp.get("/chat/<thread_id>/context")
def chat_context(thread_id: str):
    user_id = request.args.get("user", "local").strip() or "local"
    query = request.args.get("q")
    url = request.args.get("url")
    include_raw = request.args.get("include", "")
    include_tokens = {token.strip().lower() for token in include_raw.split(",") if token.strip()}
    selection = request.args.get("selection")
    title = request.args.get("title")
    locale = request.args.get("locale") or request.args.get("client_locale")
    client_time = request.args.get("time") or request.args.get("client_time")
    history_limit = request.args.get("history_limit", type=int) or 10
    metadata = {
        key: value
        for key, value in {
            "url": url,
            "title": title,
            "client_locale": (locale.strip() if isinstance(locale, str) else None),
            "client_time": (client_time.strip() if isinstance(client_time, str) else None),
        }.items()
        if isinstance(value, str) and value.strip()
    }
    metadata_payload = metadata or None
    state_db: AppStateDB = current_app.config["APP_STATE_DB"]
    context = assemble_context(
        state_db,
        user_id=user_id,
        thread_id=thread_id,
        query=query,
        url=url,
        include=include_tokens,
        selection=selection,
        metadata=metadata_payload,
        history_limit=history_limit,
    )
    return jsonify(context)


__all__ = ["bp", "store_chat_message", "chat_context"]
