"""Shadow indexing API endpoints."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

bp = Blueprint("shadow_api", __name__, url_prefix="/api/shadow")


def _get_manager():
    manager = current_app.config.get("SHADOW_INDEX_MANAGER")
    if manager is None:
        raise RuntimeError("Shadow index manager not configured")
    return manager


@bp.post("/queue")
def queue_shadow():
    payload = request.get_json(silent=True) or {}
    url = (payload.get("url") or "").strip()
    if not url:
        return jsonify({"error": "url_required"}), 400

    manager = _get_manager()
    try:
        state = manager.enqueue(url)
    except ValueError:
        return jsonify({"error": "url_required"}), 400
    return jsonify(state), 202


@bp.get("/status")
def shadow_status():
    url = (request.args.get("url") or "").strip()
    if not url:
        return jsonify({"error": "url_required"}), 400
    manager = _get_manager()
    state = manager.status(url)
    return jsonify(state), 200


__all__ = ["bp"]
