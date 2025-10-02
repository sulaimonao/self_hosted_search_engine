"""Planner endpoint executing the LangGraph state machine."""

from __future__ import annotations

import time
from typing import Any, Mapping

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
    response = {
        "ok": True,
        "duration": duration,
        "result": result,
        "events": result.get("events", []),
    }
    if result.get("langsmith_run_id"):
        response["langsmith_run_id"] = result["langsmith_run_id"]
    return jsonify(response), 200
