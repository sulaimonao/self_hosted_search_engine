"""Diagnostics-scoped aliases for self-heal planner and executor."""
from __future__ import annotations

from flask import Blueprint

from backend.app.api.self_heal import self_heal as _planner
from backend.app.api.self_heal_execute import execute_headless as _headless

bp = Blueprint("diagnostics_self_heal_api", __name__, url_prefix="/api/diagnostics")


@bp.post("/self_heal")
def diagnostics_self_heal():
    """Proxy planner requests through the diagnostics namespace."""

    return _planner()


@bp.post("/self_heal/execute_headless")
def diagnostics_self_heal_execute():
    """Proxy headless execution through the diagnostics namespace."""

    return _headless()


__all__ = ["bp"]
