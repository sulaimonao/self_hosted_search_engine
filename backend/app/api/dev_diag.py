"""Development diagnostics endpoints for the Control Center."""

from __future__ import annotations

from flask import Blueprint, Response, jsonify

from backend.app.services.runtime_status import diagnostics_snapshot, run_repairs

bp = Blueprint("dev_diag_api", __name__, url_prefix="/api/dev/diag")


@bp.get("/snapshot")
def snapshot() -> tuple[Response, int]:
    payload = diagnostics_snapshot()
    return jsonify(payload), 200


@bp.post("/repair")
def repair() -> tuple[Response, int]:
    payload = run_repairs()
    status = 200 if not payload.get("errors") else 503
    payload.setdefault("ok", status == 200)
    return jsonify(payload), status


__all__ = ["bp", "snapshot", "repair"]
