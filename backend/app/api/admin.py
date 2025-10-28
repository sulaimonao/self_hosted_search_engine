"""Minimal admin blueprint used for health checks and pytest imports."""

from __future__ import annotations

from flask import Blueprint, Response, jsonify

bp = Blueprint("admin_api", __name__, url_prefix="/api/admin")


@bp.get("/ping")
def ping() -> tuple[Response, int]:
    """Return a simple success payload used by tests."""

    return jsonify({"ok": True, "service": "admin"}), 200


__all__ = ["bp", "ping"]
