"""LLM chat endpoint streaming responses from Ollama via SSE."""

from __future__ import annotations

import json
import logging
from typing import Iterable, Iterator, List

import requests
from flask import Blueprint, Response, current_app, g, jsonify, request, stream_with_context

from server.json_logger import log_event

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


def _iter_chat_chunks(response: requests.Response, *, model: str | None) -> Iterable[str]:
    logger = _resolve_logger()
    try:
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
                    "model": model,
                }
                yield f"data: {json.dumps(final)}\n\n"
                break
    finally:
        response.close()


def _configured_models() -> tuple[str, str | None, str | None]:
    engine_config = current_app.config.get("RAG_ENGINE_CONFIG")
    primary = "gpt-oss"
    fallback: str | None = "gemma3"
    embed: str | None = "embeddinggemma"
    if engine_config is not None:
        primary = (engine_config.models.llm_primary or primary).strip() or primary
        fallback = (engine_config.models.llm_fallback or "").strip() or None
        embed = (engine_config.models.embed or embed).strip() or embed
    return primary, fallback, embed


@bp.post("/chat")
def chat_stream() -> Response:
    payload = request.get_json(silent=True) or {}
    messages = payload.get("messages")
    if not isinstance(messages, list):
        _resolve_logger().warning(
            "chat request rejected due to invalid messages payload: %s",
            type(messages).__name__,
        )
        g.chat_error_class = "ValidationError"
        g.chat_error_message = "messages must be a list"
        return jsonify({"error": "messages must be a list", "trace_id": getattr(g, "trace_id", None)}), 400
    model = (payload.get("model") or "").strip() or None

    trace_id = getattr(g, "trace_id", None)
    logger = _resolve_logger()
    logger.info(
        "chat request received model=%s prompts=%s",
        model or "<default>",
        json.dumps(_sanitize_messages(messages), ensure_ascii=False),
    )

    primary_model, fallback_model, _ = _configured_models()
    config: AppConfig = current_app.config["APP_CONFIG"]
    url = f"{config.ollama_url}/api/chat"

    attempted: list[str] = []
    missing_errors: list[str] = []
    candidates: list[str] = []
    if model:
        candidates.append(model)
    else:
        candidates.append(primary_model)
        if fallback_model and fallback_model != primary_model:
            candidates.append(fallback_model)

    body_base = {"messages": messages, "stream": True}
    selected_model: str | None = None
    fallback_used = False

    response: requests.Response | None = None
    for index, candidate in enumerate(candidates):
        attempted.append(candidate)
        attempt_body = dict(body_base)
        attempt_body["model"] = candidate
        log_event(
            "INFO",
            "chat.request",
            trace=trace_id,
            model=candidate,
            attempt=index + 1,
        )
        try:
            response = requests.post(url, json=attempt_body, stream=True, timeout=120)
        except requests.RequestException as exc:
            g.chat_error_class = exc.__class__.__name__
            g.chat_error_message = str(exc)
            logger.exception("ollama chat request failed")
            log_event(
                "ERROR",
                "chat.error",
                trace=trace_id,
                model=candidate,
                error=g.chat_error_class,
                msg=_truncate(str(exc), _MAX_ERROR_PREVIEW),
            )
            return (
                jsonify(
                    {
                        "error": "upstream_unavailable",
                        "message": str(exc),
                        "trace_id": trace_id,
                    }
                ),
                502,
            )

        if response.status_code == 404:
            content_raw = response.text.strip() or "model not found"
            reason = _truncate(content_raw, _MAX_ERROR_PREVIEW)
            logger.error(
                "ollama chat responded with HTTP 404 for model %s: %s",
                candidate,
                reason,
            )
            log_event(
                "ERROR",
                "chat.error",
                trace=trace_id,
                model=candidate,
                code=404,
                msg=reason,
            )
            missing_errors.append(reason)
            response.close()
            continue

        if response.status_code >= 400:
            content_raw = response.text.strip() or f"HTTP {response.status_code}"
            g.chat_error_class = "HTTPError"
            g.chat_error_message = _truncate(content_raw, _MAX_ERROR_PREVIEW)
            logger.error(
                "ollama chat responded with HTTP %s for model %s: %s",
                response.status_code,
                candidate,
                g.chat_error_message,
            )
            log_event(
                "ERROR",
                "chat.error",
                trace=trace_id,
                model=candidate,
                code=response.status_code,
                msg=g.chat_error_message,
            )
            response.close()
            return (
                jsonify(
                    {
                        "error": "upstream_error",
                        "status": response.status_code,
                        "message": g.chat_error_message,
                        "trace_id": trace_id,
                    }
                ),
                response.status_code,
            )

        selected_model = candidate
        fallback_used = index > 0
        break

    if selected_model is None:
        tried = [name for name in attempted if name]
        hint = "ollama pull " + " or ".join(tried or [primary_model])
        g.chat_error_class = "ModelNotFound"
        combined = missing_errors[0] if missing_errors else hint
        g.chat_error_message = combined
        log_event(
            "ERROR",
            "chat.error",
            trace=trace_id,
            model=primary_model,
            code=404,
            msg=combined,
        )
        return (
            jsonify(
                {
                    "error": "model_not_found",
                    "tried": tried,
                    "hint": hint,
                    "trace_id": trace_id,
                }
            ),
            503,
        )

    g.chat_model = selected_model
    g.chat_fallback_used = fallback_used
    g.chat_error_class = None
    g.chat_error_message = None

    def generate() -> Iterator[str]:
        yield from _iter_chat_chunks(response, model=selected_model)

    log_event(
        "INFO",
        "chat.ready",
        trace=trace_id,
        model=selected_model,
        fallback_used=fallback_used,
    )

    stream = Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
    )
    stream.headers["X-LLM-Model"] = selected_model
    return stream
