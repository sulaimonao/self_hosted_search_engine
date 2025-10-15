"""Ship-It diagnostic endpoints."""

from __future__ import annotations

from typing import Any

from flask import Blueprint, current_app, jsonify, request

from ._shipit_jobs import SimulatedJobStore, SimulatedPhase
from ..db import AppStateDB

bp = Blueprint("shipit_diag", __name__, url_prefix="/api/diag")


def _job_store() -> SimulatedJobStore:
    store: SimulatedJobStore | None = current_app.config.get("SHIPIT_JOB_STORE")
    if store is None:  # pragma: no cover - defensive
        store = SimulatedJobStore()
        current_app.config["SHIPIT_JOB_STORE"] = store
    return store


@bp.get("/models")
def diag_models() -> Any:
    engine_config = current_app.config.get("RAG_ENGINE_CONFIG")
    primary = getattr(getattr(engine_config, "models", None), "llm_primary", "gpt-oss")
    fallback = getattr(getattr(engine_config, "models", None), "llm_fallback", "gemma3")
    health = current_app.config.get(
        "SHIPIT_MODEL_HEALTH",
        {
            "primary_ok": True,
            "fallback_ok": True,
            "in_use": "primary",
        },
    )
    payload = {
        "ok": True,
        "data": {
            "primary": primary or "gpt-oss",
            "fallback": fallback or "gemma3",
            "primary_ok": bool(health.get("primary_ok", True)),
            "fallback_ok": bool(health.get("fallback_ok", True)),
            "in_use": health.get("in_use", "primary"),
        },
    }
    return jsonify(payload)


_E2E_PHASES = (
    SimulatedPhase("init", 0.5),
    SimulatedPhase("crawl", 1.5),
    SimulatedPhase("normalize", 1.0),
    SimulatedPhase("index", 1.0),
    SimulatedPhase("query", 0.5),
)


@bp.post("/e2e")
def diag_e2e_start() -> Any:
    store = _job_store()
    body = request.get_json(silent=True) or {}
    fixture_url = body.get("fixture_url")
    metadata = {"fixture_url": fixture_url or "https://example.com"}

    def builder(phase: str, pct: float, elapsed: float, _job: Any) -> dict[str, Any]:
        timings: dict[str, float] = {}
        remaining = elapsed
        for simulated in _E2E_PHASES:
            consumed = min(max(remaining, 0.0), simulated.duration_s)
            timings[simulated.name] = round(consumed, 3)
            remaining -= simulated.duration_s
        return {
            "timings": timings,
        }

    job_id = store.create(_E2E_PHASES, builder, metadata=metadata)
    payload = {"ok": True, "data": {"job_id": job_id}}
    return jsonify(payload), 202


@bp.get("/db")
def diag_db() -> Any:
    state_db = current_app.config.get("APP_STATE_DB")
    if not isinstance(state_db, AppStateDB):
        return jsonify({"ok": False, "error": "app_state_db_unavailable"}), 503
    refresh = request.args.get("refresh", "0").lower() in {"1", "true", "yes", "on"}
    snapshot = state_db.schema_diagnostics(refresh=refresh)
    status = 200 if snapshot.get("ok") else 503
    payload = {
        "ok": bool(snapshot.get("ok")),
        "data": {
            "tables": snapshot.get("tables", {}),
            "errors": snapshot.get("errors", []),
        },
    }
    if not payload["ok"]:
        payload["error"] = "schema_mismatch"
    return jsonify(payload), status


@bp.get("/e2e/status")
def diag_e2e_status() -> Any:
    job_id = (request.args.get("job_id") or "").strip()
    if not job_id:
        return jsonify({"ok": False, "error": "job_id_required"}), 400

    store = _job_store()
    snapshot = store.snapshot(job_id)
    if snapshot is None:
        return jsonify({"ok": False, "error": "job_not_found"}), 404

    timings = snapshot.get("timings") if isinstance(snapshot, dict) else None
    payload = {
        "ok": True,
        "data": {
            "phase": snapshot.get("phase"),
            "pct": snapshot.get("pct", 0),
            "timings": timings or {},
        },
    }
    if snapshot.get("error"):
        payload["data"]["error"] = snapshot["error"]
    return jsonify(payload)


__all__ = ["bp", "diag_models", "diag_e2e_start", "diag_e2e_status", "diag_db"]
