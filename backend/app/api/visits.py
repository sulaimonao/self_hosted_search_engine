"""Browser visit capture endpoints."""

from __future__ import annotations

from flask import Blueprint, current_app, request

from backend.app.db import AppStateDB

bp = Blueprint("visits_api", __name__, url_prefix="/api")


def _coerce_ms(value) -> int | None:
    try:
        if value is None:
            return None
        parsed = int(value)
        return parsed if parsed >= 0 else None
    except (TypeError, ValueError):
        return None


@bp.post("/visits")
def record_visit() -> tuple[dict, int]:
    payload = request.get_json(force=True, silent=True) or {}
    url = str(payload.get("url") or "").strip()
    if not url:
        return {"error": "url_required"}, 400
    referer = payload.get("referer")
    dur_ms = _coerce_ms(payload.get("dur_ms"))
    source = str(payload.get("source") or "browser-mode").strip() or "browser-mode"

    state_db: AppStateDB = current_app.config["APP_STATE_DB"]
    state_db.record_visit(url, referer=referer, dur_ms=dur_ms, source=source)

    enqueue = bool(payload.get("enqueue"))
    enqueue_result: dict | None = None
    if enqueue:
        shadow = current_app.config.get("SHADOW_INDEX_MANAGER")
        if shadow is not None:
            try:
                enqueue_result = shadow.enqueue(url)
            except Exception as exc:  # pragma: no cover - defensive logging only
                enqueue_result = {"error": str(exc)}

    response = {"ok": True}
    if enqueue_result:
        response["enqueue"] = enqueue_result
    return response, 201


__all__ = ["bp", "record_visit"]
