"""Diagnostics API for capturing backend and repository health snapshots."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from ..config import AppConfig
from ..jobs.diagnostics import run_diagnostics
from ..jobs.runner import JobRunner

bp = Blueprint("diagnostics_api", __name__, url_prefix="/api")


@bp.post("/diagnostics")
def diagnostics_endpoint():
    payload = request.get_json(silent=True)
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        return jsonify({"error": "JSON object body required"}), 400

    include_pytest_raw = payload.get("include_pytest")
    include_pytest: bool | None
    if include_pytest_raw is None:
        include_pytest = None
    elif isinstance(include_pytest_raw, bool):
        include_pytest = include_pytest_raw
    else:
        return jsonify({"error": "include_pytest must be a boolean"}), 400

    config: AppConfig = current_app.config["APP_CONFIG"]
    runner: JobRunner = current_app.config["JOB_RUNNER"]

    def _job() -> dict:
        return run_diagnostics(config, include_pytest=include_pytest)

    job_id = runner.submit(_job)
    return jsonify({"job_id": job_id})

