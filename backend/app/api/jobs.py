"""Job status endpoints used by the frontend for polling."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify

from ..config import AppConfig
from ..jobs.runner import JobRunner

bp = Blueprint("jobs_api", __name__, url_prefix="/api")


@bp.get("/jobs/<job_id>/status")
def job_status(job_id: str):
    runner: JobRunner = current_app.config["JOB_RUNNER"]
    payload = runner.status(job_id)
    return jsonify(payload)


@bp.get("/focused/last_index_time")
def focused_last_index_time():
    config: AppConfig = current_app.config["APP_CONFIG"]
    path = config.last_index_time_path
    if not path.exists():
        value = 0
    else:
        try:
            value = int(path.read_text("utf-8").strip() or 0)
        except Exception:
            value = 0
    return jsonify({"last_index_time": value})
