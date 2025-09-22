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

    def _parse_positive_int(value: object, field: str) -> int | None:
        if value is None:
            return None
        if isinstance(value, bool):
            raise ValueError(field)
        try:
            numeric = int(value)
        except (TypeError, ValueError):
            raise ValueError(field) from None
        if numeric <= 0:
            raise ValueError(field)
        return numeric

    try:
        budget = _parse_positive_int(payload.get("budget"), "budget")
        depth = _parse_positive_int(payload.get("depth"), "depth")
    except ValueError as exc:
        return jsonify({"error": f"invalid_{exc.args[0]}"}), 400

    force_raw = payload.get("force")
    force = bool(force_raw) if force_raw is not None else False

    seeds_payload = payload.get("seeds")
    seeds: list[str] | None
    if seeds_payload is None:
        seeds = None
    else:
        seeds_list: list[str] = []
        if isinstance(seeds_payload, str):
            candidate = seeds_payload.strip()
            if candidate:
                seeds_list.append(candidate)
        elif isinstance(seeds_payload, (list, tuple)):
            for item in seeds_payload:
                if not isinstance(item, str):
                    return jsonify({"error": "invalid_seeds"}), 400
                candidate = item.strip()
                if candidate:
                    seeds_list.append(candidate)
        else:
            return jsonify({"error": "invalid_seeds"}), 400
        seeds = seeds_list

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

