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

    budget_raw = payload.get("budget")
    budget: int | None
    if budget_raw is None:
        budget = None
    else:
        try:
            budget = int(budget_raw)
        except (TypeError, ValueError):
            return jsonify({"error": "invalid_budget"}), 400
        if budget <= 0:
            return jsonify({"error": "invalid_budget"}), 400

    depth_raw = payload.get("depth")
    depth: int | None
    if depth_raw is None:
        depth = None
    else:
        try:
            depth = int(depth_raw)
        except (TypeError, ValueError):
            return jsonify({"error": "invalid_depth"}), 400
        if depth <= 0:
            return jsonify({"error": "invalid_depth"}), 400

    force_raw = payload.get("force")
    force = bool(force_raw) if force_raw is not None else False

    seeds_payload = payload.get("seeds")
    seeds: list[str] | None = None
    if seeds_payload is not None:
        cleaned: list[str] = []
        if isinstance(seeds_payload, str):
            cleaned.append(seeds_payload)
        elif isinstance(seeds_payload, (list, tuple, set)):
            for item in seeds_payload:
                if isinstance(item, str):
                    value = item.strip()
                    if value:
                        cleaned.append(value)
        else:
            return jsonify({"error": "invalid_seeds"}), 400
        seeds = cleaned if cleaned else None

    try:
        job_id, status, created = worker.enqueue(
            query,
            use_llm=use_llm,
            model=model,
            budget=budget,
            depth=depth,
            force=force,
            seeds=seeds,
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

