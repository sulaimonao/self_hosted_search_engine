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
    state_db.ensure_llm_thread(thread_id, origin="chat")
    stored_id = state_db.add_chat_message(
        message_id=message_id,
        thread_id=thread_id,
        role=role,
        content=content,
        tokens=tokens_value,
    )
    metadata: dict[str, str] | None = None
    page_url = payload.get("page_url")
    if isinstance(page_url, str) and page_url.strip():
        metadata = {"page_url": page_url.strip()}
    state_db.append_llm_message(
        thread_id=thread_id,
        role=role,
        content=content,
        message_id=stored_id,
        tokens=tokens_value,
        metadata=metadata,
    )
    return jsonify({"ok": True, "id": stored_id})


@bp.route("/chat/<thread_id>/context", methods=["GET", "POST"])
def chat_context(thread_id: str):
    def _normalize_string(value: object | None) -> str | None:
        if isinstance(value, str):
            candidate = value.strip()
            return candidate or None
        return None

    def _normalize_include(raw: object | None) -> set[str]:
        tokens: set[str] = set()
        entries: list[str] = []
        if isinstance(raw, str):
            entries = raw.split(",")
        elif isinstance(raw, (list, tuple, set)):
            entries = [str(item) for item in raw]
        for entry in entries:
            token = entry.strip().lower()
            if token:
                tokens.add(token)
        return tokens

    def _coerce_int(value: object | None, fallback: int = 10) -> int:
        try:
            if isinstance(value, bool):
                raise ValueError("bool")
            parsed = int(value)  # type: ignore[arg-type]
            return parsed
        except (TypeError, ValueError):
            return fallback

    extra_metadata: dict[str, str] | None = None

    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        user_id = (
            _normalize_string(payload.get("user") or payload.get("user_id")) or "local"
        )
        query = _normalize_string(payload.get("q") or payload.get("query"))
        url = _normalize_string(payload.get("url"))
        include_raw = payload.get("include")
        selection = _normalize_string(payload.get("selection"))
        title = _normalize_string(payload.get("title"))
        locale = _normalize_string(
            payload.get("locale") or payload.get("client_locale")
        )
        client_time = _normalize_string(
            payload.get("time") or payload.get("client_time")
        )
        history_limit = _coerce_int(payload.get("history_limit"), fallback=10)
        metadata_payload = payload.get("metadata")
        if isinstance(metadata_payload, dict):
            extra_metadata = {
                str(key): str(value)
                for key, value in metadata_payload.items()
                if isinstance(key, str) and isinstance(value, str) and value.strip()
            }
    else:
        user_id = _normalize_string(request.args.get("user")) or "local"
        query = _normalize_string(request.args.get("q"))
        url = _normalize_string(request.args.get("url"))
        include_raw = request.args.get("include", "")
        selection = _normalize_string(request.args.get("selection"))
        title = _normalize_string(request.args.get("title"))
        locale = _normalize_string(
            request.args.get("locale") or request.args.get("client_locale")
        )
        client_time = _normalize_string(
            request.args.get("time") or request.args.get("client_time")
        )
        history_limit = request.args.get("history_limit", type=int) or 10

    include_tokens = _normalize_include(include_raw)
    metadata = {
        key: value
        for key, value in {
            "url": url,
            "title": title,
            "client_locale": locale,
            "client_time": client_time,
        }.items()
        if isinstance(value, str) and value.strip()
    }
    metadata_payload = metadata or None
    if extra_metadata:
        metadata_payload = {**(metadata_payload or {}), **extra_metadata}
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
