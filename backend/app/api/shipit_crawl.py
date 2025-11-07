"""Ship-It crawl control endpoints."""

from __future__ import annotations

from typing import Any

from flask import Blueprint, current_app, jsonify, request

from ._shipit_jobs import SimulatedJobStore, SimulatedPhase

bp = Blueprint("shipit_crawl", __name__, url_prefix="/api/crawl")


def _job_store() -> SimulatedJobStore:
    store: SimulatedJobStore | None = current_app.config.get("SHIPIT_JOB_STORE")
    if store is None:  # pragma: no cover - defensive
        store = SimulatedJobStore()
        current_app.config["SHIPIT_JOB_STORE"] = store
    return store


_CRAWL_PHASES = (
    SimulatedPhase("queued", 0.5),
    SimulatedPhase("fetching", 1.5),
    SimulatedPhase("parsing", 1.0),
    SimulatedPhase("normalizing", 1.0),
    SimulatedPhase("indexing", 0.5),
    SimulatedPhase("cleaning", 0.2),
)


def _crawl_builder(phase: str, pct: float, elapsed: float, job: Any) -> dict[str, Any]:
    metadata = dict(getattr(job, "metadata", {}))
    total_urls = int(metadata.get("estimated_urls", 25))
    processed = min(total_urls, int(total_urls * (pct / 100.0)))
    last_url = None
    if processed > 0:
        seed = (metadata.get("seeds") or ["https://example.com"])[0]
        last_url = f"{seed.rstrip('/')}/doc/{processed}"
    eta = max(int(job.total_duration - elapsed), 0) if job.total_duration else 0
    return {
        "urls_processed": processed,
        "last_url": last_url,
        "eta_s": eta,
        "errors": [],
    }


@bp.get("/status")
def crawl_status() -> Any:
    job_id = (request.args.get("job_id") or "").strip()
    if not job_id:
        return jsonify({"ok": False, "error": "job_id_required"}), 400

    store = _job_store()
    try:
        snapshot = store.snapshot(job_id)
    except KeyError:
        return jsonify({"ok": False, "error": "job_not_found"}), 404
    if snapshot is None:
        return jsonify({"ok": False, "error": "job_not_found"}), 404

    payload = {"ok": True, "data": snapshot}
    return jsonify(payload)


def create_crawl_job(seeds: list[str], mode: str) -> str:
    store = _job_store()
    estimated_urls = max(len(seeds) * 8, 25)
    metadata = {"seeds": seeds, "mode": mode, "estimated_urls": estimated_urls}
    return store.create(_CRAWL_PHASES, _crawl_builder, metadata=metadata)


__all__ = ["bp", "crawl_status", "create_crawl_job"]
