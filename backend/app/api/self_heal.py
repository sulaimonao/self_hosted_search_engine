"""Self-heal orchestrator: accepts BrowserIncident and returns an AutopilotDirective."""
from __future__ import annotations

from typing import Any, Mapping

from flask import Blueprint, jsonify, request

from backend.app.api.schemas import AutopilotDirective
from backend.app.api.reasoning import route_to_browser  # noqa: F401 - imported for future integration

bp = Blueprint("self_heal_api", __name__, url_prefix="/api")


def _coerce_incident(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": str(payload.get("id") or ""),
        "url": str(payload.get("url") or ""),
        "symptoms": dict(payload.get("symptoms") or {}),
        "domSnippet": (payload.get("domSnippet") or "")[:4000],
    }


@bp.post("/self_heal")
def self_heal():
    """Plan or apply a safe, permissioned fix."""

    apply = request.args.get("apply", "false").lower() in {"1", "true", "yes", "on"}
    incident = _coerce_incident(request.get_json(silent=True) or {})

    banner_text = (
        str((incident.get("symptoms") or {}).get("bannerText") or "").strip() or None
    )
    reload_reason = "Fallback: reload the page to clear transient UI errors."
    if banner_text:
        reload_reason = f"{reload_reason} Last banner: {banner_text}"

    directive = AutopilotDirective(
        reason=reload_reason,
        steps=[{"type": "reload"}],
    )
    mode = "apply" if apply else "plan"
    return jsonify({"mode": mode, "directive": directive.model_dump()}), 200
