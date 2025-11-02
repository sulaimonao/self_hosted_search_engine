"""Runtime health and capability endpoints."""

from __future__ import annotations

from flask import Blueprint, Response, jsonify

from backend.app.services.runtime_status import (
    build_capability_snapshot,
    build_health_snapshot,
)

bp = Blueprint("runtime_api", __name__, url_prefix="/api")


@bp.get("/health")
def health() -> tuple[Response, int]:
    payload = build_health_snapshot()
    status = payload.get("status")
    code = 200 if status in {"ok", "degraded"} else 503
    return jsonify(payload), code


@bp.get("/capabilities")
def capabilities() -> tuple[Response, int]:
    payload = build_capability_snapshot()
    return jsonify(payload), 200


__all__ = ["bp", "health", "capabilities"]
