"""LLM chat endpoint streaming responses from Ollama via SSE."""

from __future__ import annotations

import json
import logging
from typing import Iterable, Iterator, List

import requests
from flask import Blueprint, Response, current_app, request, stream_with_context

from ..config import AppConfig

bp = Blueprint("chat_api", __name__, url_prefix="/api")


LOGGER = logging.getLogger(__name__)
_MAX_LOGGED_MESSAGES = 5
_MAX_MESSAGE_PREVIEW = 200
_MAX_ERROR_PREVIEW = 500


def _resolve_logger() -> logging.Logger:
    """Return the logger configured for chat telemetry."""

    try:
        app = current_app._get_current_object()
    except RuntimeError:  # pragma: no cover - fallback for out-of-context use
        return LOGGER
    configured = app.config.get("CHAT_LOGGER")
    if configured is not None:
        return configured
    return app.logger


def _truncate(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    return value[: max_length - 3] + "..."


def _sanitize_messages(messages: List[dict]) -> list[dict[str, object]]:
    sanitized: list[dict[str, object]] = []
    for message in messages[:_MAX_LOGGED_MESSAGES]:
        if not isinstance(message, dict):
            sanitized.append({"type": type(message).__name__})
            continue
        role = message.get("role")
        role_str = role if isinstance(role, str) else repr(role)
        content = message.get("content")
        if isinstance(content, str):
            preview = _truncate(content, _MAX_MESSAGE_PREVIEW)
            char_count: int | None = len(content)
        elif content is None:
            preview = ""
            char_count = 0
        else:
            preview = _truncate(str(content), _MAX_MESSAGE_PREVIEW)
            char_count = None
        sanitized.append({
            "role": role_str,
            "preview": preview,
            "chars": char_count,
        })
    if len(messages) > _MAX_LOGGED_MESSAGES:
        sanitized.append({"omitted": len(messages) - _MAX_LOGGED_MESSAGES})
    return sanitized


def _ollama_chat_stream(url: str, payload: dict) -> Iterable[str]:
    logger = _resolve_logger()
    logger.info(
        "forwarding chat request to ollama url=%s model=%s",
        url,
        payload.get("model") or "<default>",
    )
    try:
        response = requests.post(url, json=payload, stream=True, timeout=120)
    except requests.RequestException as exc:
        logger.exception("ollama chat request failed")
        message = json.dumps({"type": "error", "content": str(exc)})
        yield f"data: {message}\n\n"
        return

    if response.status_code >= 400:
        content_raw = response.text.strip() or f"HTTP {response.status_code}"
        content = _truncate(content_raw, _MAX_ERROR_PREVIEW)
        logger.error(
            "ollama chat responded with HTTP %s: %s",
            response.status_code,
            content,
        )
        message = json.dumps({"type": "error", "content": content})
        yield f"data: {message}\n\n"
        return

    for line in response.iter_lines():
        if not line:
            continue
        try:
            chunk = json.loads(line.decode("utf-8"))
        except json.JSONDecodeError:
            logger.debug("discarding non-json chunk from ollama: %s", line)
            continue
        message = chunk.get("message", {})
        content = message.get("content")
        if content:
            yield f"data: {json.dumps({'type': 'token', 'content': content})}\n\n"
        if chunk.get("done"):
            final = {
                "type": "done",
                "total_duration": chunk.get("total_duration"),
                "load_duration": chunk.get("load_duration"),
            }
            yield f"data: {json.dumps(final)}\n\n"
            break


@bp.post("/chat")
def chat_stream() -> Response:
    payload = request.get_json(silent=True) or {}
    messages = payload.get("messages")
    if not isinstance(messages, list):
        _resolve_logger().warning(
            "chat request rejected due to invalid messages payload: %s",
            type(messages).__name__,
        )
        return Response(
            json.dumps({"error": "messages must be a list"}),
            status=400,
            mimetype="application/json",
        )
    model = (payload.get("model") or "").strip() or None

    logger = _resolve_logger()
    logger.info(
        "chat request received model=%s prompts=%s",
        model or "<default>",
        json.dumps(_sanitize_messages(messages), ensure_ascii=False),
    )

    config: AppConfig = current_app.config["APP_CONFIG"]
    url = f"{config.ollama_url}/api/chat"
    body = {"messages": messages, "stream": True}
    if model:
        body["model"] = model

    def generate() -> Iterator[str]:
        yield from _ollama_chat_stream(url, body)

    return Response(stream_with_context(generate()), mimetype="text/event-stream")
