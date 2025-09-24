"""Job status endpoints used by the frontend for polling."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request, send_file

from ..config import AppConfig
from ..jobs.runner import JobRunner

bp = Blueprint("jobs_api", __name__, url_prefix="/api")


@bp.get("/jobs/<job_id>/status")
def job_status(job_id: str):
    runner: JobRunner = current_app.config["JOB_RUNNER"]
    payload = runner.status(job_id)
    return jsonify(payload)


@bp.get("/jobs/<job_id>/log")
def job_log(job_id: str):
    runner: JobRunner = current_app.config["JOB_RUNNER"]
    path = runner.log_path(job_id)
    if path is None:
        return jsonify({"error": "Log not found"}), 404

    resolved = path if path.is_absolute() else path.resolve()
    if not resolved.exists():
        return jsonify({"error": "Log not found"}), 404

    download = request.args.get("download", "1").lower() not in {"0", "false", "no"}
    response = send_file(resolved, mimetype="text/plain", as_attachment=download)
    if download:
        response.headers["Content-Disposition"] = f'attachment; filename="{job_id}.log"'
    return response


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
