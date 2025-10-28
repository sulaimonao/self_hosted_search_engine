"""HTTP endpoints exposing the deep-research agent tools."""

from __future__ import annotations

import time

from flask import Blueprint, current_app, jsonify, request

from observability import start_span

from .utils import coerce_chat_identifier
from ..services.agent_tracing import publish_agent_step

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
    started_at = time.time()
    chat_id = coerce_chat_identifier(
        request.headers.get("X-Chat-Id") or payload.get("chat_id")
    )
    message_id = coerce_chat_identifier(request.headers.get("X-Message-Id"))
    query = (payload.get("query") or "").strip()
    if not query:
        publish_agent_step(
            tool="agent.search_index",
            chat_id=chat_id,
            message_id=message_id,
            args={"query": query},
            status="error",
            started_at=started_at,
            ended_at=time.time(),
            excerpt="query is required",
        )
        return jsonify({"error": "query is required"}), 400

    k, error = _parse_int(payload.get("k", 20), default=20, min_value=1, max_value=100)
    if error:
        publish_agent_step(
            tool="agent.search_index",
            chat_id=chat_id,
            message_id=message_id,
            args={"query": query, "k": payload.get("k")},
            status="error",
            started_at=started_at,
            ended_at=time.time(),
            excerpt="invalid k",
        )
        return (
            jsonify({"error": "k must be an integer between 1 and 100"}),
            400,
        )

    use_embeddings = _parse_bool(payload.get("use_embeddings", True), default=True)

    results = _runtime().search_index(query, k=k, use_embeddings=use_embeddings)
    publish_agent_step(
        tool="agent.search_index",
        chat_id=chat_id,
        message_id=message_id,
        args={"query": query, "k": k, "use_embeddings": use_embeddings},
        status="ok",
        started_at=started_at,
        ended_at=time.time(),
        excerpt=f"{len(results)} results",
    )
    return jsonify({"results": results}), 200


@bp.post("/enqueue_crawl")
def enqueue_crawl() -> tuple[str, int]:
    payload = request.get_json(silent=True) or {}
    started_at = time.time()
    chat_id = coerce_chat_identifier(
        request.headers.get("X-Chat-Id") or payload.get("chat_id")
    )
    message_id = coerce_chat_identifier(request.headers.get("X-Message-Id"))
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
            publish_agent_step(
                tool="agent.enqueue_crawl",
                chat_id=chat_id,
                message_id=message_id,
                args={"priority": inputs.get("priority"), "topic": inputs.get("topic")},
                status="error",
                started_at=started_at,
                ended_at=time.time(),
                excerpt="url is required",
            )
            return jsonify({"error": "url is required"}), 400

        priority, priority_error = _parse_float(
            payload.get("priority", 0.5), default=0.5, min_value=0.0, max_value=1.0
        )
        if priority_error == "invalid":
            publish_agent_step(
                tool="agent.enqueue_crawl",
                chat_id=chat_id,
                message_id=message_id,
                args={"url": url, "priority": payload.get("priority")},
                status="error",
                started_at=started_at,
                ended_at=time.time(),
                excerpt="priority must be a number",
            )
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
        publish_agent_step(
            tool="agent.enqueue_crawl",
            chat_id=chat_id,
            message_id=message_id,
            args={"url": url, "priority": priority, "topic": topic},
            status="ok" if queued else "skipped",
            started_at=started_at,
            ended_at=time.time(),
            excerpt="queued" if queued else "not queued",
        )
        return jsonify({"queued": queued}), 200


@bp.post("/fetch_page")
def fetch_page() -> tuple[str, int]:
    payload = request.get_json(silent=True) or {}
    started_at = time.time()
    chat_id = coerce_chat_identifier(
        request.headers.get("X-Chat-Id") or payload.get("chat_id")
    )
    message_id = coerce_chat_identifier(request.headers.get("X-Message-Id"))
    url = (payload.get("url") or "").strip()
    if not url:
        publish_agent_step(
            tool="agent.fetch_page",
            chat_id=chat_id,
            message_id=message_id,
            args={"url": url},
            status="error",
            started_at=started_at,
            ended_at=time.time(),
            excerpt="url is required",
        )
        return jsonify({"error": "url is required"}), 400
    result = _runtime().fetch_page(url)
    publish_agent_step(
        tool="agent.fetch_page",
        chat_id=chat_id,
        message_id=message_id,
        args={"url": url},
        status="ok" if result.get("status") else "skipped",
        started_at=started_at,
        ended_at=time.time(),
        excerpt=result.get("title") or result.get("status"),
    )
    return jsonify(result), 200


@bp.post("/reindex")
def reindex() -> tuple[str, int]:
    payload = request.get_json(silent=True) or {}
    started_at = time.time()
    chat_id = coerce_chat_identifier(
        request.headers.get("X-Chat-Id") or payload.get("chat_id")
    )
    message_id = coerce_chat_identifier(request.headers.get("X-Message-Id"))
    batch = payload.get("batch")
    with start_span(
        "http.tools.reindex",
        attributes={"http.route": "/api/tools/reindex", "http.method": request.method},
        inputs={"batch_size": len(batch) if isinstance(batch, (list, tuple)) else None},
    ):
        if not isinstance(batch, (list, tuple)):
            publish_agent_step(
                tool="agent.reindex",
                chat_id=chat_id,
                message_id=message_id,
                args={"batch_size": None},
                status="error",
                started_at=started_at,
                ended_at=time.time(),
                excerpt="batch must be an array",
            )
            return jsonify({"error": "batch must be an array"}), 400

        urls = []
        for item in batch:
            text = str(item).strip()
            if text:
                urls.append(text)

        if not urls:
            publish_agent_step(
                tool="agent.reindex",
                chat_id=chat_id,
                message_id=message_id,
                args={"batch_size": 0},
                status="error",
                started_at=started_at,
                ended_at=time.time(),
                excerpt="empty batch",
            )
            return jsonify({"error": "batch must contain at least one url"}), 400

        result = _runtime().reindex(urls)
        publish_agent_step(
            tool="agent.reindex",
            chat_id=chat_id,
            message_id=message_id,
            args={"batch_size": len(urls)},
            status="ok",
            started_at=started_at,
            ended_at=time.time(),
            excerpt=result,
        )
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
