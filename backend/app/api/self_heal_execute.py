"""Endpoints for executing headless self-heal directives."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Dict, Mapping, Optional

import json
import logging
from flask import Blueprint, current_app, jsonify, request

from backend.app.agent.executor import run_headless
from backend.app.exec.headless_executor import HeadlessExecutionError, HeadlessResult
from backend.app.io import coerce_directive
from backend.app.io.models import Directive, VERB_MAP
from backend.app.self_heal.episodes import append_episode
from backend.app.self_heal.metrics import record_event
from backend.app.services.progress_bus import ProgressBus

bp = Blueprint("self_heal_headless_api", __name__, url_prefix="/api/self_heal")

_DIAGNOSTIC_JOB_ID = "__diagnostics__"

LOGGER = logging.getLogger(__name__)


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


def _shrink_payload(value: Any, *, max_string: int = 512, max_items: int = 20) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _shrink_payload(v, max_string=max_string, max_items=max_items) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [
            _shrink_payload(item, max_string=max_string, max_items=max_items)
            for item in list(value)[:max_items]
        ]
    if isinstance(value, str):
        if len(value) > max_string:
            return value[: max_string - 3] + "..."
        return value
    return value


def _payload_preview(payload: Any, *, limit: int = 900) -> str:
    try:
        rendered = json.dumps(payload, ensure_ascii=False)
    except (TypeError, ValueError):
        rendered = str(payload)
    if len(rendered) > limit:
        return rendered[: limit - 3] + "..."
    return rendered


def _publish_payload(stage: str, payload: Any, *, trace_id: str | None = None) -> None:
    event: Dict[str, Any] = {
        "stage": stage,
        "kind": "payload",
        "payload": _shrink_payload(payload),
        "preview": _payload_preview(payload),
    }
    if trace_id:
        event["trace_id"] = trace_id
    _publish(event)


def _coerce_directive(payload: Any) -> Directive:
    return coerce_directive(payload)


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


def _filter_directive_steps(directive: Directive) -> Dict[str, Any]:
    steps = directive.steps or []
    if not steps:
        return {"steps": []}
    selected: set[int] = set()
    prefix_types = {"navigate", "waitForStable", "reload"}
    last_headless_idx: Optional[int] = None
    for idx, step in enumerate(steps):
        payload = step.as_payload()
        step_type = str(payload.get("type") or "").strip()
        if step_type not in VERB_MAP.values():
            continue
        if bool(payload.get("headless")):
            selected.add(idx)
            last_headless_idx = idx
            prefix_idx = idx - 1
            while prefix_idx >= 0:
                prev_payload = steps[prefix_idx].as_payload()
                prev_type = str(prev_payload.get("type") or "").strip()
                if prev_type not in prefix_types:
                    break
                selected.add(prefix_idx)
                prefix_idx -= 1
        elif step_type == "waitForStable" and last_headless_idx is not None and idx >= last_headless_idx:
            selected.add(idx)

    filtered = [steps[i].as_payload() for i in sorted(selected)]
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
    trace_id = request.headers.get("X-Trace-Id") or request.headers.get("X-Request-Id")
    _publish_payload("headless.request", filtered_directive, trace_id=trace_id)
    _publish(
        {
            "stage": "headless",
            "status": "start",
            "message": "Headless execution requested.",
            "steps": len(filtered_directive.get("steps", [])),
            "trace_id": trace_id,
        }
    )
    LOGGER.info(
        "self_heal.headless.start",
        extra={
            "trace_id": trace_id,
            "steps": len(filtered_directive.get("steps", [])),
            "base_url": base_url,
        },
    )

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
        error_payload = {"ok": False, "error": message}
        if trace_id:
            error_payload["trace_id"] = trace_id
        LOGGER.info(
            "self_heal.headless.error",
            extra={"trace_id": trace_id, "error": message},
        )
        return jsonify(error_payload), 500
    except Exception as exc:  # pragma: no cover - defensive guard
        message = str(exc)
        _publish({"stage": "headless", "status": "error", "message": message})
        try:
            record_event("headless_runs_count", bus=_progress_bus())
        except Exception:  # pragma: no cover - best effort
            pass
        error_payload = {"ok": False, "error": message}
        if trace_id:
            error_payload["trace_id"] = trace_id
        LOGGER.info(
            "self_heal.headless.error",
            extra={"trace_id": trace_id, "error": message},
        )
        return jsonify(error_payload), 500

    steps_payload = _result_to_events(result)
    response: Dict[str, Any] = {"ok": result.ok, "steps": steps_payload}
    if result.failed_step is not None:
        response["failed_step"] = result.failed_step
    if result.session_id:
        response["session_id"] = result.session_id
    if trace_id:
        response["trace_id"] = trace_id

    status_code = 200 if result.ok else 500
    meta = {
        "session_id": result.session_id,
        "failed_step": result.failed_step,
        "ok": result.ok,
    }
    if trace_id:
        meta["trace_id"] = trace_id
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
    _publish_payload("headless.response", response, trace_id=trace_id)
    LOGGER.info(
        "self_heal.headless.complete",
        extra={
            "trace_id": trace_id,
            "ok": result.ok,
            "failed_step": result.failed_step,
            "steps": len(steps_payload),
        },
    )
    return jsonify(response), status_code


@bp.get("/ping")
def self_heal_ping():
    trace_id = request.headers.get("X-Trace-Id") or request.headers.get("X-Request-Id")
    base_url = request.host_url.rstrip("/")
    directive = {
        "steps": [
            {"type": "navigate", "url": "https://example.org", "headless": True},
            {"type": "reload", "headless": True},
        ]
    }
    try:
        result = run_headless(directive, base_url=base_url, sse_publish=None)
    except HeadlessExecutionError as exc:
        payload = {"ok": False, "error": str(exc)}
        if trace_id:
            payload["trace_id"] = trace_id
        return jsonify(payload), 503
    except Exception as exc:  # pragma: no cover - defensive guard
        payload = {"ok": False, "error": str(exc)}
        if trace_id:
            payload["trace_id"] = trace_id
        return jsonify(payload), 500

    summary = _result_to_payload(result)
    response_payload: Dict[str, Any] = {
        "ok": result.ok,
        "steps": len(summary.get("steps", [])),
        "result": summary,
    }
    if result.failed_step is not None:
        response_payload["failed_step"] = result.failed_step
    if trace_id:
        response_payload["trace_id"] = trace_id
    status = 200 if result.ok else 500
    return jsonify(response_payload), status


@bp.post("/headless_apply")
def headless_apply():
    body = request.get_json(silent=True) or {}
    directive = _coerce_directive(body.get("directive"))
    context = body.get("context") if isinstance(body.get("context"), Mapping) else {}

    filtered_directive = _filter_directive_steps(directive)
    steps = filtered_directive.get("steps") if isinstance(filtered_directive.get("steps"), list) else []
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
            filtered_directive,
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
    _publish_payload("headless.response", response_payload)
    return jsonify(response_payload), status_code


__all__ = ["bp"]
