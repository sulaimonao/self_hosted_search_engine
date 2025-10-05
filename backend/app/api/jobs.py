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


@bp.get("/crawl/start")
def crawl_start():
    worker = current_app.config.get("REFRESH_WORKER")
    if worker is None:
        return jsonify({"error": "refresh_unavailable"}), 503

    seed_id = request.args.get("seed_id", "").strip()
    url = request.args.get("url", "").strip()
    query = request.args.get("query", "").strip()
    force = request.args.get("force", "0").lower() in {"1", "true", "yes", "on"}

    seeds: list[str] = []
    if url:
        seeds.append(url)
        if not query:
            query = url
    if seed_id:
        seeds.append(seed_id)
        if not query:
            query = seed_id

    query = query.strip()
    if not query:
        return jsonify({"error": "missing_query"}), 400

    try:
        job_id, status, created = worker.enqueue(
            query,
            use_llm=False,
            model=None,
            seeds=seeds or None,
            force=force,
        )
    except ValueError as exc:
        return jsonify({"error": "invalid_query", "detail": str(exc)}), 400

    response = {
        "job_id": job_id,
        "created": bool(created),
        "status": "queued",
        "seeds": seeds,
    }
    if isinstance(status, dict):
        response["status"] = status.get("state") or "queued"
        if status.get("message"):
            response["message"] = status["message"]
    return jsonify(response)
