"""Deep research API wiring requests into background jobs."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from ..config import AppConfig
from ..jobs.research import run_research
from ..jobs.runner import JobRunner

bp = Blueprint("research_api", __name__, url_prefix="/api")


@bp.post("/research")
def research_endpoint():
    payload = request.get_json(silent=True) or {}
    query = (payload.get("query") or "").strip()
    model = (payload.get("model") or "").strip() or None

    budget_raw = payload.get("budget")
    budget = 20
    if budget_raw not in (None, ""):
        try:
            if isinstance(budget_raw, str):
                trimmed = budget_raw.strip()
                if trimmed:
                    budget = int(trimmed)
            else:
                budget = int(budget_raw)
        except (TypeError, ValueError):
            return jsonify({"error": "invalid_budget"}), 400

    if not query:
        return jsonify({"error": "query is required"}), 400

    budget = max(1, min(100, budget))

    config: AppConfig = current_app.config["APP_CONFIG"]
    runner: JobRunner = current_app.config["JOB_RUNNER"]

    def _job():
        return run_research(query, model, budget, config=config)

    job_id = runner.submit(_job)
    return jsonify({"job_id": job_id})
