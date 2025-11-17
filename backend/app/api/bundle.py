"""Bundle import/export endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from flask import Blueprint, abort, current_app, jsonify, request

from backend.app.db import AppStateDB
from backend.app.services import bundle_io

bp = Blueprint("bundle_api", __name__, url_prefix="/api")


def _state_db() -> AppStateDB:
    state_db = current_app.config.get("APP_STATE_DB")
    if not isinstance(state_db, AppStateDB):  # pragma: no cover - misconfiguration
        abort(500, "app state database unavailable")
    return state_db


def _bundle_dir() -> Path:
    override = current_app.config.get("BUNDLE_STORAGE_DIR")
    if override:
        base = Path(override)
    else:
        app_config = current_app.config.get("APP_CONFIG")
        if app_config is not None and getattr(app_config, "agent_data_dir", None):
            base = Path(app_config.agent_data_dir) / "bundles"
        else:
            base = Path("/tmp") / "shse-bundles"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")


@bp.get("/export/bundle")
def export_bundle_endpoint():
    state_db = _state_db()
    components = request.args.getlist("component") or None
    job_id = state_db.create_job(
        "bundle_export",
        payload={"components": components} if components else None,
    )
    state_db.update_job(job_id, status="running", started_at=_now_iso())
    try:
        bundle_path, manifest = bundle_io.export_bundle(
            state_db,
            _bundle_dir(),
            components=components,
        )
    except Exception as exc:
        state_db.update_job(job_id, status="failed", error=str(exc), completed_at=_now_iso())
        raise
    state_db.update_job(
        job_id,
        status="succeeded",
        completed_at=_now_iso(),
        result={"bundle_path": str(bundle_path), "manifest": manifest},
    )
    return jsonify(
        {
            "job_id": job_id,
            "bundle_path": str(bundle_path),
            "manifest": manifest,
        }
    )


@bp.post("/import/bundle")
def import_bundle_endpoint():
    state_db = _state_db()
    payload = request.get_json(force=True, silent=True) or {}
    bundle_path = payload.get("bundle_path")
    if not bundle_path:
        abort(400, "bundle_path is required")
    components = payload.get("components")
    job_id = state_db.create_job(
        "bundle_import",
        payload={"bundle_path": bundle_path, "components": components},
    )
    state_db.update_job(job_id, status="running", started_at=_now_iso())
    try:
        stats = bundle_io.import_bundle(state_db, Path(bundle_path), components=components)
    except FileNotFoundError:
        state_db.update_job(job_id, status="failed", error="bundle_not_found", completed_at=_now_iso())
        abort(404, "bundle file not found")
    except ValueError as exc:
        state_db.update_job(job_id, status="failed", error=str(exc), completed_at=_now_iso())
        abort(400, str(exc))
    state_db.update_job(
        job_id,
        status="succeeded",
        completed_at=_now_iso(),
        result={"imported": stats},
    )
    return jsonify({"job_id": job_id, "imported": stats})

