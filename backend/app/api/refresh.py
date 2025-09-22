"""Manual refresh API wiring the background worker into Flask."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

bp = Blueprint("refresh_api", __name__, url_prefix="/api/refresh")


def _get_worker():
    return current_app.config.get("REFRESH_WORKER")


@bp.post("")
def trigger_refresh():
    worker = _get_worker()
    if worker is None:
        return jsonify({"error": "refresh_unavailable"}), 503

    payload = request.get_json(silent=True) or {}
    query = (payload.get("query") or "").strip()
    if not query:
        return jsonify({"error": "missing_query"}), 400

    use_llm_raw = payload.get("use_llm")
    use_llm = bool(use_llm_raw) if use_llm_raw is not None else False
    model = payload.get("model")
    if isinstance(model, str):
        model = model.strip() or None
    else:
        model = None

    try:
        job_id, status, created = worker.enqueue(query, use_llm=use_llm, model=model)
    except ValueError as exc:
        return jsonify({"error": "invalid_query", "detail": str(exc)}), 400

    response = {"job_id": job_id, "status": status, "created": created}
    if not created:
        response["deduplicated"] = True
    return jsonify(response), 202 if created else 200


@bp.get("/status")
def refresh_status():
    worker = _get_worker()
    if worker is None:
        return jsonify({"error": "refresh_unavailable"}), 503

    job_id = request.args.get("job_id")
    query = request.args.get("query")
    snapshot = worker.status(job_id=job_id, query=query)
    return jsonify(snapshot)

