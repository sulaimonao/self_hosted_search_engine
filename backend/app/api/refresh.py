"""Manual refresh API wiring the background worker into Flask."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

bp = Blueprint("refresh_api", __name__, url_prefix="/api/refresh")


def _get_worker():
    return current_app.config.get("REFRESH_WORKER")


def _get_config():
    return current_app.config.get("APP_CONFIG")


@bp.post("")
def trigger_refresh():
    worker = _get_worker()
    if worker is None:
        return jsonify({"error": "refresh_unavailable"}), 503

    payload = request.get_json(silent=True) or {}
    query = (payload.get("query") or "").strip()
    if not query:
        return jsonify({"error": "missing_query"}), 400

    config = _get_config()

    budget_value = payload.get("budget")
    try:
        budget = int(budget_value)
    except (TypeError, ValueError):
        budget = None
    if budget is None or budget <= 0:
        budget = getattr(config, "focused_budget", 10)

    depth_value = payload.get("depth")
    try:
        depth = int(depth_value)
    except (TypeError, ValueError):
        depth = None
    if depth is None or depth <= 0:
        depth = getattr(config, "focused_depth", 2)

    seeds_payload = payload.get("seeds")
    seeds: list[str] = []
    if isinstance(seeds_payload, (list, tuple)):
        for item in seeds_payload:
            if isinstance(item, str):
                candidate = item.strip()
                if candidate:
                    seeds.append(candidate)

    force_raw = payload.get("force")
    force = bool(force_raw) if force_raw is not None else False

    use_llm_raw = payload.get("use_llm")
    use_llm = bool(use_llm_raw) if use_llm_raw is not None else False
    model = payload.get("model")
    if isinstance(model, str):
        model = model.strip() or None
    else:
        model = None

    try:
        job_id, status, created = worker.enqueue(
            query,
            budget=budget,
            depth=depth,
            force=force,
            seeds=seeds,
            use_llm=use_llm,
            model=model,
        )
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

