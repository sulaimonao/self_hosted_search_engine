"""Shadow indexing API endpoints."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

bp = Blueprint("shadow_api", __name__, url_prefix="/api/shadow")


def _get_manager():
    return current_app.config.get("SHADOW_INDEX_MANAGER")


def _manager_or_unavailable():
    manager = _get_manager()
    if manager is None:
        return None, (jsonify({"error": "shadow_unavailable"}), 503)
    return manager, None


def _coerce_enabled(value) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "on", "yes"}:
            return True
        if normalized in {"0", "false", "off", "no"}:
            return False
    return None


@bp.get("")
def shadow_config():
    manager, error_response = _manager_or_unavailable()
    if error_response is not None:
        return error_response

    config = manager.get_config()
    return jsonify(config), 200


@bp.post("")
def update_shadow_config():
    manager, error_response = _manager_or_unavailable()
    if error_response is not None:
        return error_response

    payload = request.get_json(silent=True) or {}
    enabled_value = _coerce_enabled(payload.get("enabled"))
    if enabled_value is None:
        return jsonify({"error": "invalid_enabled"}), 400

    config = manager.set_enabled(enabled_value)
    return jsonify(config), 200


@bp.post("/queue")
def queue_shadow():
    payload = request.get_json(silent=True) or {}
    url = (payload.get("url") or "").strip()
    if not url:
        return jsonify({"error": "url_required"}), 400

    manager, error_response = _manager_or_unavailable()
    if error_response is not None:
        return error_response
    try:
        state = manager.enqueue(url)
    except ValueError:
        return jsonify({"error": "url_required"}), 400
    except RuntimeError as exc:
        if str(exc) == "shadow_disabled":
            return jsonify({"error": "shadow_disabled"}), 409
        raise
    return jsonify(state), 202


@bp.get("/status")
def shadow_status():
    url = (request.args.get("url") or "").strip()
    if not url:
        return jsonify({"error": "url_required"}), 400
    manager, error_response = _manager_or_unavailable()
    if error_response is not None:
        return error_response
    state = manager.status(url)
    return jsonify(state), 200


__all__ = ["bp"]
