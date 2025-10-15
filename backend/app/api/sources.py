"""API endpoints for managing source-follow settings and state."""

from __future__ import annotations

from http import HTTPStatus

from flask import Blueprint, Response, current_app, jsonify, request

from backend.app.db import AppStateDB

bp = Blueprint("sources", __name__, url_prefix="/api/sources")


def _state_db() -> AppStateDB:
    state_db = current_app.config.get("APP_STATE_DB")
    if not isinstance(state_db, AppStateDB):  # pragma: no cover - defensive
        raise RuntimeError("application state database unavailable")
    return state_db


@bp.get("/config")
def get_sources_config() -> Response:
    config = _state_db().get_sources_config()
    return jsonify({"config": config.to_dict()})


@bp.post("/config")
def update_sources_config() -> Response:
    payload = request.get_json(silent=True)
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        return jsonify({"error": "invalid_payload"}), HTTPStatus.BAD_REQUEST
    config = _state_db().set_sources_config(payload)
    return jsonify({"config": config.to_dict(), "ok": True})
