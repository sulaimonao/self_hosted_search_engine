"""Endpoints for executing headless self-heal directives."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Dict, Mapping, Optional

from flask import Blueprint, current_app, jsonify, request

from backend.app.agent.executor import run_headless
from backend.app.exec.headless_executor import HeadlessExecutionError, HeadlessResult
from backend.app.self_heal.episodes import append_episode
from backend.app.self_heal.metrics import record_event
from backend.app.services.progress_bus import ProgressBus

bp = Blueprint("self_heal_headless_api", __name__, url_prefix="/api/self_heal")

_DIAGNOSTIC_JOB_ID = "__diagnostics__"


def _publish(event: Dict[str, Any]) -> None:
    bus: ProgressBus | None = current_app.config.get("PROGRESS_BUS")
    if isinstance(bus, ProgressBus):
        bus.publish(_DIAGNOSTIC_JOB_ID, event)


def _progress_bus() -> ProgressBus | None:
    try:
        bus = current_app.config.get("PROGRESS_BUS")
    except RuntimeError:  # pragma: no cover - defensive guard for teardown
        return None
    return bus if isinstance(bus, ProgressBus) else None


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


def _result_to_events(result: HeadlessResult) -> list[Dict[str, Any]]:
    events: list[Dict[str, Any]] = []
    for record in result.steps:
        payload: Dict[str, Any] = {
            "index": record.index,
            "type": record.type,
            "status": record.status,
            "args": record.args,
            "elapsed_ms": record.elapsed_ms,
        }
        if record.detail is not None:
            payload["detail"] = record.detail
        if record.response is not None:
            payload["response"] = record.response
        events.append(payload)
    return events


def _filter_directive_steps(directive: Dict[str, Any]) -> Dict[str, Any]:
    steps = directive.get("steps")
    if not isinstance(steps, list):
        return {"steps": []}
    selected: set[int] = set()
    prefix_types = {"navigate", "waitForStable", "reload"}
    last_headless_idx: Optional[int] = None
    for idx, raw in enumerate(steps):
        if not isinstance(raw, Mapping):
            continue
        step_type = str(raw.get("type") or raw.get("verb") or "").strip()
        if bool(raw.get("headless")):
            selected.add(idx)
            last_headless_idx = idx
            prefix_idx = idx - 1
            while prefix_idx >= 0:
                prev = steps[prefix_idx]
                if not isinstance(prev, Mapping):
                    break
                prev_type = str(prev.get("type") or prev.get("verb") or "").strip()
                if prev_type not in prefix_types:
                    break
                selected.add(prefix_idx)
                prefix_idx -= 1
        elif step_type == "waitForStable" and last_headless_idx is not None and idx >= last_headless_idx:
            selected.add(idx)

    filtered = [dict(steps[i]) for i in sorted(selected)]
    return {"steps": filtered}


@bp.post("/execute_headless")
def execute_headless():
    payload = request.get_json(silent=True) or {}
    directive = _coerce_directive(payload.get("directive"))
    consent = bool(payload.get("consent"))

    if not consent:
        return jsonify({"ok": False, "error": "consent_required"}), 400

    base_url = request.host_url.rstrip("/")
    filtered_directive = _filter_directive_steps(directive)

    def _sse_publish(event: Dict[str, Any]) -> None:
        try:
            _publish(event)
        except Exception:  # pragma: no cover - diagnostics best-effort
            pass

    try:
        result = run_headless(
            filtered_directive,
            base_url=base_url,
            sse_publish=_sse_publish,
        )
    except HeadlessExecutionError as exc:
        message = str(exc)
        _publish({"stage": "headless", "status": "error", "message": message})
        try:
            record_event("headless_runs_count", bus=_progress_bus())
        except Exception:  # pragma: no cover - best effort
            pass
        return jsonify({"ok": False, "error": message}), 500
    except Exception as exc:  # pragma: no cover - defensive guard
        message = str(exc)
        _publish({"stage": "headless", "status": "error", "message": message})
        try:
            record_event("headless_runs_count", bus=_progress_bus())
        except Exception:  # pragma: no cover - best effort
            pass
        return jsonify({"ok": False, "error": message}), 500

    steps_payload = _result_to_events(result)
    response: Dict[str, Any] = {"ok": result.ok, "steps": steps_payload}
    if result.failed_step is not None:
        response["failed_step"] = result.failed_step
    if result.session_id:
        response["session_id"] = result.session_id

    status_code = 200 if result.ok else 500
    meta = {
        "session_id": result.session_id,
        "failed_step": result.failed_step,
        "ok": result.ok,
    }
    try:
        record_event("headless_runs_count", bus=_progress_bus())
    except Exception:  # pragma: no cover
        pass
    try:
        append_episode(
            url="",
            symptoms={},
            directive=filtered_directive,
            mode="headless",
            outcome="success" if result.ok else "fail",
            details={"failed_step": result.failed_step} if result.failed_step is not None else {},
            meta=meta,
        )
    except Exception:  # pragma: no cover
        pass
    return jsonify(response), status_code


@bp.post("/headless_apply")
def headless_apply():
    body = request.get_json(silent=True) or {}
    directive = _coerce_directive(body.get("directive"))
    context = body.get("context") if isinstance(body.get("context"), Mapping) else {}

    steps = directive.get("steps") if isinstance(directive.get("steps"), list) else []
    if not steps:
        return jsonify({"ok": False, "events": [], "error": "no_headless_steps"}), 400

    raw_session: Optional[str] = None
    if isinstance(context, Mapping):
        sid_value = context.get("session_id")
        if isinstance(sid_value, str):
            raw_session = sid_value.strip() or None

    base_url = request.host_url.rstrip("/")

    def _sse_publish(event: Dict[str, Any]) -> None:
        _publish(event)

    try:
        result = run_headless(
            _filter_directive_steps(directive),
            base_url=base_url,
            session_id=raw_session,
            sse_publish=_sse_publish,
        )
    except Exception as exc:  # pragma: no cover - defensive guard
        message = str(exc)
        _publish({"stage": "headless", "status": "error", "message": message})
        return jsonify({"ok": False, "events": [], "error": message}), 500

    response_payload: Dict[str, Any] = {
        "ok": result.ok,
        "events": _result_to_events(result),
        "session_id": result.session_id,
        "failed_step": result.failed_step,
        "last_state": result.last_state,
        "transcript": result.transcript,
    }
    if not result.ok:
        response_payload["error"] = "headless_execution_failed"

    status_code = 200 if result.ok else 500
    return jsonify(response_payload), status_code


__all__ = ["bp"]
