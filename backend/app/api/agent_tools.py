"""HTTP endpoints exposing the deep-research agent tools."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

bp = Blueprint("agent_tools", __name__, url_prefix="/api/tools")


def _runtime():
    runtime = current_app.config.get("AGENT_RUNTIME")
    if runtime is None:  # pragma: no cover - runtime always configured in app factory
        raise RuntimeError("Agent runtime not configured")
    return runtime


@bp.post("/search_index")
def search_index() -> tuple[str, int]:
    payload = request.get_json(silent=True) or {}
    query = (payload.get("query") or "").strip()
    k = int(payload.get("k", 20))
    use_embeddings = bool(payload.get("use_embeddings", True))
    results = _runtime().search_index(query, k=k, use_embeddings=use_embeddings)
    return jsonify({"results": results}), 200


@bp.post("/enqueue_crawl")
def enqueue_crawl() -> tuple[str, int]:
    payload = request.get_json(silent=True) or {}
    url = (payload.get("url") or "").strip()
    if not url:
        return jsonify({"error": "url is required"}), 400
    priority = float(payload.get("priority", 0.5))
    topic = payload.get("topic")
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
    urls = [str(item).strip() for item in batch] if isinstance(batch, (list, tuple)) else None
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
