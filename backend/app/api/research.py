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
    budget = int(payload.get("budget") or 20)
    if not query:
        return jsonify({"error": "query is required"}), 400
    budget = max(1, min(100, budget))

    config: AppConfig = current_app.config["APP_CONFIG"]
    runner: JobRunner = current_app.config["JOB_RUNNER"]

    def _job():
        return run_research(query, model, budget, config=config)

    job_id = runner.submit(_job)
    return jsonify({"job_id": job_id})
