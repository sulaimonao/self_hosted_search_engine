"""Endpoints for executing headless self-heal directives."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Dict, Mapping

from flask import Blueprint, current_app, jsonify, request

from backend.app.exec.headless_executor import HeadlessResult, run as run_headless
from backend.app.services.progress_bus import ProgressBus

bp = Blueprint("self_heal_headless_api", __name__, url_prefix="/api/self_heal")

_DIAGNOSTIC_JOB_ID = "__diagnostics__"


def _publish(event: Dict[str, Any]) -> None:
    bus: ProgressBus | None = current_app.config.get("PROGRESS_BUS")
    if isinstance(bus, ProgressBus):
        bus.publish(_DIAGNOSTIC_JOB_ID, event)


def _coerce_directive(payload: Any) -> Dict[str, Any]:
    if isinstance(payload, Mapping):
        return dict(payload)
    return {}


def _result_to_payload(result: HeadlessResult) -> Dict[str, Any]:
    steps_payload = []
    for item in result.steps:
        if is_dataclass(item):
            steps_payload.append(asdict(item))
        else:
            steps_payload.append(dict(item))
    response: Dict[str, Any] = {
        "status": "ok" if result.ok else "error",
        "failed_step": result.failed_step,
        "session_id": result.session_id,
        "steps": steps_payload,
        "last_state": result.last_state,
        "transcript": result.transcript,
    }
    return response


@bp.post("/execute_headless")
def execute_headless():
    payload = request.get_json(silent=True) or {}
    consent = bool(payload.get("consent"))
    directive = _coerce_directive(payload.get("directive"))

    if not consent:
        return jsonify({"status": "denied", "error": "consent_required"}), 400

    base_url = request.host_url.rstrip("/")

    def _sse_publish(event: Dict[str, Any]) -> None:
        _publish(event)

    try:
        result = run_headless(
            directive,
            base_url=base_url,
            sse_publish=_sse_publish,
        )
    except Exception as exc:  # pragma: no cover - defensive guard
        error_payload = {
            "status": "error",
            "error": str(exc),
        }
        _publish({"stage": "headless", "status": "error", "message": str(exc)})
        return jsonify(error_payload), 500

    response = _result_to_payload(result)
    status_code = 200 if result.ok else 500
    return jsonify(response), status_code


__all__ = ["bp"]
