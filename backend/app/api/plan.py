"""Planner endpoint executing the LangGraph state machine."""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from typing import Any

from flask import Blueprint, Response, current_app, jsonify, request

from observability import start_span

bp = Blueprint("plan_api", __name__, url_prefix="/api")


def _normalize_context(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


@bp.post("/plan")
def execute_plan() -> Response:
    payload = request.get_json(silent=True) or {}
    query = payload.get("query")
    if not isinstance(query, str) or not query.strip():
        return jsonify({"ok": False, "error": "query is required"}), 400
    query_text = query.strip()
    context = _normalize_context(payload.get("context"))
    model = payload.get("model") if isinstance(payload.get("model"), str) else None
    planner = current_app.config.get("RAG_PLANNER_AGENT")
    if planner is None:
        return jsonify({"ok": False, "error": "planner unavailable"}), 503
    start = time.perf_counter()
    with start_span("planner.plan", attributes={"query_length": len(query_text)}):
        try:
            result = planner.run(query_text, context=context, model=model)
        except Exception as exc:  # pragma: no cover - defensive logging
            current_app.logger.exception("planner execution failed")
            return jsonify({"ok": False, "error": str(exc)}), 500

    duration = time.perf_counter() - start
    result_payload = result if isinstance(result, Mapping) else {}
    events = result_payload.get("events")
    if isinstance(events, Sequence) and not isinstance(events, (str, bytes, bytearray)):
        events_list = list(events)
    else:
        events_list = []
    response = {
        "ok": True,
        "duration": duration,
        "result": result,
        "events": events_list,
    }
    langsmith_run_id = result_payload.get("langsmith_run_id")
    if isinstance(langsmith_run_id, str) and langsmith_run_id:
        response["langsmith_run_id"] = langsmith_run_id
    return jsonify(response), 200
