"""History persistence API."""

from __future__ import annotations

from datetime import datetime

from flask import Blueprint, abort, current_app, jsonify, request

from backend.app.db import AppStateDB

bp = Blueprint("history_api", __name__, url_prefix="/api/history")


def _state_db() -> AppStateDB:
    state_db = current_app.config.get("APP_STATE_DB")
    if not isinstance(state_db, AppStateDB):
        abort(503, "app state database unavailable")
    return state_db


@bp.post("/visit")
def record_visit():
    payload = request.get_json(force=True, silent=True) or {}
    url = str(payload.get("url") or "").strip()
    if not url:
        return jsonify({"error": "url_required"}), 400
    title = payload.get("title")
    referrer = payload.get("referrer")
    status_code = payload.get("status_code")
    content_type = payload.get("content_type")
    tab_id_raw = payload.get("tab_id") or payload.get("tabId")
    tab_id = str(tab_id_raw).strip() if tab_id_raw is not None else None
    visited_at = payload.get("visited_at") or payload.get("visitedAt")

    state_db = _state_db()
    record = {
        "tab_id": tab_id,
        "url": url,
        "title": title,
        "referrer": referrer,
        "status_code": status_code,
        "content_type": content_type,
        "visited_at": visited_at,
        "shadow_enqueued": False,
    }
    history_id = state_db.import_browser_history_record(record)
    return jsonify({"id": history_id, "tab_id": tab_id, "url": url}), 201


@bp.get("/list")
def list_history():
    state_db = _state_db()
    limit = request.args.get("limit", type=int) or 200
    query = request.args.get("query")
    start = request.args.get("from")
    end = request.args.get("to")
    try:
        items = state_db.query_history(limit=limit, query=query, start=_parse_iso(start), end=_parse_iso(end))
    except Exception:  # pragma: no cover - defensive guard
        current_app.logger.exception("history.list_failed")
        items = []
    return jsonify({"items": items})


def _parse_iso(value: str | None):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


__all__ = ["bp"]
