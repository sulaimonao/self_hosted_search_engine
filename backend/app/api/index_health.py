"""Endpoints exposing index health diagnostics and rebuild controls."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from ..services.index_health import probe_all, rebuild


bp = Blueprint("index_health", __name__, url_prefix="/api/index")


@bp.get("/health")
def index_health() -> tuple[dict, int]:
    payload = probe_all()
    return jsonify(payload), 200


@bp.post("/rebuild")
def index_rebuild() -> tuple[dict, int]:
    payload = request.get_json(silent=True) or {}
    store = payload.get("store") if isinstance(payload, dict) else None
    result = rebuild(store)
    status = 202 if result.get("accepted") else 503
    return jsonify(result), status


__all__ = ["bp", "index_health", "index_rebuild"]
