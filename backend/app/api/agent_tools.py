"""HTTP endpoints exposing the deep-research agent tools."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from observability import start_span

bp = Blueprint("agent_tools", __name__, url_prefix="/api/tools")


def _runtime():
    runtime = current_app.config.get("AGENT_RUNTIME")
    if runtime is None:  # pragma: no cover - runtime always configured in app factory
        raise RuntimeError("Agent runtime not configured")
    return runtime


def _parse_int(value, *, default: int, min_value: int | None = None, max_value: int | None = None) -> tuple[int, str | None]:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default, "invalid"
    if min_value is not None and number < min_value:
        return default, "too_small"
    if max_value is not None and number > max_value:
        return default, "too_large"
    return number, None


def _parse_float(
    value,
    *,
    default: float,
    min_value: float | None = None,
    max_value: float | None = None,
) -> tuple[float, str | None]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default, "invalid"
    if min_value is not None:
        number = max(min_value, number)
    if max_value is not None:
        number = min(max_value, number)
    return number, None


def _parse_bool(value, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "y", "on"}:
            return True
        if lowered in {"false", "0", "no", "n", "off"}:
            return False
    return default


@bp.post("/search_index")
def search_index() -> tuple[str, int]:
    payload = request.get_json(silent=True) or {}
    query = (payload.get("query") or "").strip()
    if not query:
        return jsonify({"error": "query is required"}), 400

    k, error = _parse_int(payload.get("k", 20), default=20, min_value=1, max_value=100)
    if error:
        return (
            jsonify({"error": "k must be an integer between 1 and 100"}),
            400,
        )

    use_embeddings = _parse_bool(payload.get("use_embeddings", True), default=True)

    results = _runtime().search_index(query, k=k, use_embeddings=use_embeddings)
    return jsonify({"results": results}), 200


@bp.post("/enqueue_crawl")
def enqueue_crawl() -> tuple[str, int]:
    payload = request.get_json(silent=True) or {}
    inputs = {
        "url": payload.get("url"),
        "priority": payload.get("priority"),
        "topic": payload.get("topic"),
    }
    with start_span(
        "http.tools.enqueue_crawl",
        attributes={"http.route": "/api/tools/enqueue_crawl", "http.method": request.method},
        inputs=inputs,
    ):
        url = (payload.get("url") or "").strip()
        if not url:
            return jsonify({"error": "url is required"}), 400

        priority, priority_error = _parse_float(
            payload.get("priority", 0.5), default=0.5, min_value=0.0, max_value=1.0
        )
        if priority_error == "invalid":
            return jsonify({"error": "priority must be a number"}), 400

        topic_raw = payload.get("topic")
        topic = topic_raw.strip() if isinstance(topic_raw, str) else None
        reason = payload.get("reason")
        source_task_id = payload.get("source_task_id")
        queued = _runtime().enqueue_crawl(
            url,
            priority=priority,
            topic=topic,
            reason=reason,
            source_task_id=source_task_id,
        )
        return jsonify({"queued": queued}), 200


@bp.post("/fetch_page")
def fetch_page() -> tuple[str, int]:
    payload = request.get_json(silent=True) or {}
    url = (payload.get("url") or "").strip()
    if not url:
        return jsonify({"error": "url is required"}), 400
    result = _runtime().fetch_page(url)
    return jsonify(result), 200


@bp.post("/reindex")
def reindex() -> tuple[str, int]:
    payload = request.get_json(silent=True) or {}
    batch = payload.get("batch")
    with start_span(
        "http.tools.reindex",
        attributes={"http.route": "/api/tools/reindex", "http.method": request.method},
        inputs={"batch_size": len(batch) if isinstance(batch, (list, tuple)) else None},
    ):
        if not isinstance(batch, (list, tuple)):
            return jsonify({"error": "batch must be an array"}), 400

        urls = []
        for item in batch:
            text = str(item).strip()
            if text:
                urls.append(text)

        if not urls:
            return jsonify({"error": "batch must contain at least one url"}), 400

        result = _runtime().reindex(urls)
        return jsonify(result), 200


@bp.get("/status")
def status() -> tuple[str, int]:
    result = _runtime().status()
    return jsonify(result), 200


@bp.post("/agent/turn")
def agent_turn() -> tuple[str, int]:
    payload = request.get_json(silent=True) or {}
    query = (payload.get("query") or "").strip()
    if not query:
        return jsonify({"error": "query is required"}), 400
    result = _runtime().handle_turn(query)
    return jsonify(result), 200
