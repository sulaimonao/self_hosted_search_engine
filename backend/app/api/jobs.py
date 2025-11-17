"""Job status endpoints used by the frontend for polling."""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any, Dict

from flask import Blueprint, current_app, jsonify, request, send_file

from ..config import AppConfig
from ..db import AppStateDB
from ..jobs.runner import JobRunner

bp = Blueprint("jobs_api", __name__, url_prefix="/api")


@bp.get("/jobs")
def list_jobs():
    """Return job records with optional status/type filtering."""

    state_db: AppStateDB = current_app.config["APP_STATE_DB"]
    limit = request.args.get("limit", type=int) or 50
    status = request.args.get("status")
    job_type = request.args.get("type")
    if job_type:
        job_type = job_type.strip() or None
    items = state_db.list_jobs(limit=limit, status=status, job_type=job_type)
    return jsonify({"items": items})


@bp.get("/jobs/<job_id>")
def get_job(job_id: str):
    state_db: AppStateDB = current_app.config["APP_STATE_DB"]
    record = state_db.get_job(job_id)
    if not record:
        return jsonify({"error": "not_found"}), 404
    return jsonify({"job": record})


def _compose_job_status(job_id: str) -> dict[str, Any]:
    worker = current_app.config.get("REFRESH_WORKER")
    if worker is not None:
        status_snapshot = worker.status(job_id=job_id)
        job_snapshot: Mapping[str, Any] | None = None
        if isinstance(status_snapshot, Mapping):
            candidate = status_snapshot.get("job")
            if isinstance(candidate, Mapping):
                job_snapshot = candidate
        if job_snapshot:
            payload = _format_refresh_job(dict(job_snapshot))
            return payload
    runner: JobRunner = current_app.config["JOB_RUNNER"]
    payload = runner.status(job_id)
    state_db: AppStateDB = current_app.config["APP_STATE_DB"]
    db_status = state_db.get_job_status(job_id)
    if db_status:
        steps_total = int(db_status.get("steps_total") or 0)
        steps_completed = int(db_status.get("steps_completed") or 0)
        progress = payload.get("progress")
        if steps_total > 0:
            progress = max(0.0, min(1.0, steps_completed / steps_total))
        merged = dict(payload)
        merged.update(
            {
                "phase": db_status.get("phase") or merged.get("phase"),
                "steps_total": steps_total,
                "steps_completed": steps_completed,
                "retries": int(db_status.get("retries") or 0),
                "eta_seconds": db_status.get("eta_seconds"),
                "message": db_status.get("message") or merged.get("message"),
                "started_at": db_status.get("started_at"),
                "updated_at": db_status.get("updated_at"),
                "url": db_status.get("url") or merged.get("url"),
                "progress": progress,
            }
        )
        return merged
    return payload


@bp.get("/jobs/<job_id>/status")
def job_status(job_id: str):
    payload = _compose_job_status(job_id)
    return jsonify(payload)


@bp.get("/jobs/<job_id>/progress")
def job_progress(job_id: str):
    payload = _compose_job_status(job_id)
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


def _format_refresh_job(job: Dict[str, Any]) -> Dict[str, Any]:
    state = str(job.get("state") or "unknown")
    stage = str(job.get("stage") or "queued")
    stats = job.get("stats") or {}
    if not isinstance(stats, dict):
        stats = {}
    started_at = job.get("started_at")
    if isinstance(started_at, (int, float)):
        elapsed = max(0.0, time.time() - float(started_at))
    else:
        elapsed = None
    progress_pct = float(job.get("progress") or 0.0)
    eta_seconds = None
    if state == "running" and elapsed is not None and progress_pct > 0:
        remaining = max(0.0, 100.0 - progress_pct)
        eta_seconds = max(0.0, (elapsed * remaining) / max(progress_pct, 1e-6))

    payload: Dict[str, Any] = {
        "job_id": job.get("id") or job.get("job_id") or job.get("jobId") or "",
        "state": state,
        "phase": stage,
        "progress": max(0.0, min(1.0, progress_pct / 100.0)),
        "eta_seconds": eta_seconds,
        "stats": {
            "pages_fetched": int(stats.get("pages_fetched", 0) or 0),
            "normalized_docs": int(stats.get("normalized_docs", 0) or 0),
            "docs_indexed": int(stats.get("docs_indexed", 0) or 0),
            "skipped": int(stats.get("skipped", 0) or 0),
            "deduped": int(stats.get("deduped", 0) or 0),
            "embedded": int(stats.get("embedded", 0) or 0),
        },
        "started_at": started_at,
        "updated_at": job.get("updated_at"),
        "message": job.get("message"),
        "error": job.get("error"),
    }

    return payload


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
