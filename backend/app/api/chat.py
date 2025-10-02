"""LLM chat endpoint returning structured responses from Ollama."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Iterable, Mapping

import requests
from flask import Blueprint, Response, current_app, g, jsonify, request

from server.json_logger import log_event

from ..config import AppConfig
from ..services import ollama_client

bp = Blueprint("chat_api", __name__, url_prefix="/api")

LOGGER = logging.getLogger(__name__)
_MAX_ERROR_PREVIEW = 500
_MAX_CONTEXT_CHARS = 8_000
_SCHEMA_PROMPT = (
    "You are a helpful assistant embedded in a self-hosted search engine. "
    "Always reply with strict JSON containing only the keys reasoning, answer, and citations (an array of strings). "
    "Keep reasoning concise (<=6 sentences). Place the final user-facing reply in answer. "
    "Include citations when you reference external facts; omit when not applicable."
)
_JSON_FORMAT_ALLOWLIST: tuple[str, ...] = ()


def _truncate(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    return value[: max_length - 3] + "..."


def _sanitize_messages(messages: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    sanitized: list[dict[str, Any]] = []
    for raw in messages:
        if not isinstance(raw, Mapping):
            continue
        role = raw.get("role")
        content = raw.get("content")
        if isinstance(role, str) and isinstance(content, str):
            entry: dict[str, Any] = {"role": role, "content": content}
            if "images" in raw and isinstance(raw["images"], list):
                entry["images"] = [str(item) for item in raw["images"] if isinstance(item, str)]
            sanitized.append(entry)
    return sanitized


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


def _supports_json_format(model: str) -> bool:
    normalized = (model or "").lower()
    return any(normalized.startswith(prefix) for prefix in _JSON_FORMAT_ALLOWLIST)


def _first_string_value(value: Any) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, Mapping):
        for item in value.values():
            found = _first_string_value(item)
            if found:
                return found
    elif isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray)):
        for item in value:
            found = _first_string_value(item)
            if found:
                return found
    return ""


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped[3:]
        if stripped.startswith("json"):
            stripped = stripped[4:]
        if "```" in stripped:
            stripped = stripped.split("```", 1)[0]
    return stripped.strip()


def _coerce_schema(text: str) -> dict[str, Any]:
    candidate = _strip_code_fence(text)
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = candidate[start : end + 1]
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError as exc:  # pragma: no cover - repair attempts best effort
        raise ValueError(f"Model response was not valid JSON: {exc}") from exc

    reasoning = data.get("reasoning")
    if not isinstance(reasoning, str):
        for key in ("thinking", "thoughts", "chain_of_thought"):
            alt = data.get(key)
            if isinstance(alt, str):
                reasoning = alt
                break
        else:
            reasoning = json.dumps(reasoning) if reasoning is not None else ""
    reasoning = reasoning.strip()
    if not reasoning:
        filtered = {k: v for k, v in data.items() if k not in {"citations", "answer", "response", "output", "final_answer", "message"}}
        reasoning = _first_string_value(filtered)

    answer = data.get("answer")
    if not isinstance(answer, str):
        for key in ("response", "output", "final_answer", "message"):
            alt = data.get(key)
            if isinstance(alt, str):
                answer = alt
                break
        else:
            if answer is None:
                answer = _first_string_value(data)
            else:
                fallback_answer = _first_string_value(answer)
                answer = fallback_answer or json.dumps(answer)
            if not answer:
                answer = ""
    answer = answer.strip()
    if not answer:
        filtered = {k: v for k, v in data.items() if k not in {"citations", "reasoning", "thinking", "thoughts", "chain_of_thought"}}
        answer = _first_string_value(filtered)

    citations = data.get("citations")

    if isinstance(citations, str):
        citations_list = [citations]
    elif isinstance(citations, Iterable):
        citations_list = [str(item) for item in citations if isinstance(item, (str, int, float))]
        citations_list = [item for item in citations_list if item]
    else:
        citations_list = []

    return {
        "reasoning": reasoning.strip(),
        "answer": answer.strip(),
        "citations": citations_list,
    }


def _extract_model_content(payload: Mapping[str, Any]) -> str:
    message = payload.get("message")
    if isinstance(message, Mapping):
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content
    response_field = payload.get("response")
    if isinstance(response_field, str) and response_field.strip():
        return response_field
    raise ValueError("Upstream response missing assistant content")


def _extract_model_reasoning(payload: Mapping[str, Any]) -> str:
    message = payload.get("message")
    if isinstance(message, Mapping):
        for key in ("reasoning", "thinking"):
            raw = message.get(key)
            if isinstance(raw, str) and raw.strip():
                return raw
    reasoning_field = payload.get("reasoning")
    if isinstance(reasoning_field, str) and reasoning_field.strip():
        return reasoning_field
    return ""


def _prepare_messages(
    *,
    candidate: str,
    base_messages: list[dict[str, Any]],
    url: str | None,
    text_context: str | None,
    image_context: str | None,
) -> tuple[list[dict[str, Any]], bool, str]:
    messages = [dict(message) for message in base_messages]

    context_bits: list[str] = []
    if url:
        context_bits.append(f"Current page URL: {url}")
    if text_context:
        clipped = text_context[:_MAX_CONTEXT_CHARS]
        context_bits.append("Extracted page text:\n" + clipped)

    system_sections = [_SCHEMA_PROMPT]
    if context_bits:
        system_sections.append("\n\n".join(context_bits))
    system_prompt = "\n\n".join(section for section in system_sections if section)

    image_used = False
    if image_context and ollama_client.supports_vision(candidate):
        messages.insert(
            0,
            {
                "role": "user",
                "content": "Image context captured from the current page.",
                "images": [image_context],
            },
        )
        image_used = True

    return messages, image_used, system_prompt


def _chat_endpoint(config: AppConfig) -> str:
    return f"{config.ollama_url.rstrip('/')}/api/chat"


def _consume_streaming_response(response: requests.Response) -> Mapping[str, Any]:
    """Return the final payload from a streaming Ollama response with merged content."""

    last_payload: Mapping[str, Any] | None = None
    accumulated_content = ""
    last_content_chunk = ""
    accumulated_reasoning = ""
    last_reasoning_chunk = ""

    for raw_line in response.iter_lines():
        if not raw_line:
            continue
        try:
            decoded = raw_line.decode("utf-8")
        except UnicodeDecodeError:  # pragma: no cover - defensive guard
            LOGGER.debug("Ignoring undecodable chat chunk: %r", raw_line)
            continue
        try:
            payload = json.loads(decoded)
        except ValueError:
            LOGGER.debug("Ignoring non-JSON chat chunk: %s", decoded)
            continue
        if not isinstance(payload, Mapping):
            continue
        last_payload = payload
        message = payload.get("message")
        if not isinstance(message, Mapping):
            continue

        content = message.get("content")
        if isinstance(content, str) and content:
            if last_content_chunk and content.startswith(last_content_chunk):
                delta = content[len(last_content_chunk) :]
                if delta:
                    accumulated_content += delta
            elif accumulated_content and content.startswith(accumulated_content):
                delta = content[len(accumulated_content) :]
                if delta:
                    accumulated_content += delta
            elif last_content_chunk and last_content_chunk.startswith(content):
                # The stream repeated an earlier prefix; treat as no-op.
                pass
            else:
                accumulated_content += content
            last_content_chunk = content

        reasoning_value = None
        for key in ("reasoning", "thinking"):
            value = message.get(key)
            if isinstance(value, str) and value:
                reasoning_value = value
                break
        if reasoning_value:
            if last_reasoning_chunk and reasoning_value.startswith(last_reasoning_chunk):
                delta = reasoning_value[len(last_reasoning_chunk) :]
                if delta:
                    accumulated_reasoning += delta
            elif accumulated_reasoning and reasoning_value.startswith(accumulated_reasoning):
                delta = reasoning_value[len(accumulated_reasoning) :]
                if delta:
                    accumulated_reasoning += delta
            elif last_reasoning_chunk and last_reasoning_chunk.startswith(reasoning_value):
                pass
            else:
                accumulated_reasoning += reasoning_value
            last_reasoning_chunk = reasoning_value

    if last_payload is None:
        raise ValueError("Upstream response stream was empty")

    merged = dict(last_payload)
    message = dict(merged.get("message") or {})
    if accumulated_content:
        message["content"] = accumulated_content
    elif isinstance(message.get("content"), str):
        # Preserve whatever content we last observed, even if empty string.
        message["content"] = message.get("content")
    if accumulated_reasoning:
        message["reasoning"] = accumulated_reasoning
    merged["message"] = message
    return merged


@bp.post("/chat")
def chat_invoke() -> Response:
    start = time.perf_counter()
    payload = request.get_json(silent=True) or {}
    messages_raw = payload.get("messages")
    if not isinstance(messages_raw, list):
        g.chat_error_class = "ValidationError"
        g.chat_error_message = "messages must be a list"
        return jsonify({"error": "messages must be a list", "trace_id": getattr(g, "trace_id", None)}), 400

    sanitized_messages = _sanitize_messages(messages_raw)
    if not sanitized_messages:
        g.chat_error_class = "ValidationError"
        g.chat_error_message = "messages must contain at least one message"
        return jsonify({"error": "messages must contain at least one message", "trace_id": getattr(g, "trace_id", None)}), 400

    chat_logger = current_app.config.get("CHAT_LOGGER")
    if hasattr(chat_logger, "info"):
        preview = " | ".join(
            entry.get("content", "") for entry in sanitized_messages if isinstance(entry.get("content"), str)
        )
        chat_logger.info("chat request received: %s", preview.strip())

    requested_model = (payload.get("model") or "").strip() or None
    url_value = (payload.get("url") or "").strip() or None
    text_context = (payload.get("text_context") or "").strip() or None
    image_context_raw = payload.get("image_context")
    image_context = image_context_raw if isinstance(image_context_raw, str) and image_context_raw.strip() else None

    trace_id = getattr(g, "trace_id", None)
    primary_model, fallback_model, _ = _configured_models()

    candidates: list[str] = []
    if requested_model:
        candidates.append(requested_model)
    else:
        candidates.append(primary_model)
        if fallback_model and fallback_model != primary_model:
            candidates.append(fallback_model)

    config: AppConfig = current_app.config["APP_CONFIG"]
    endpoint = _chat_endpoint(config)

    attempted: list[str] = []
    missing_reasons: list[str] = []

    for attempt_index, candidate in enumerate(candidates, start=1):
        attempted.append(candidate)
        prepared_messages, image_used, system_prompt = _prepare_messages(
            candidate=candidate,
            base_messages=sanitized_messages,
            url=url_value,
            text_context=text_context,
            image_context=image_context,
        )

        log_event(
            "INFO",
            "chat.request",
            trace=trace_id,
            model=candidate,
            attempt=attempt_index,
            url=url_value,
            has_text=bool(text_context),
            has_img=bool(image_context),
        )

        if hasattr(chat_logger, "info"):
            chat_logger.info("forwarding chat request to ollama (model=%s)", candidate)

        request_payload: dict[str, Any] = {
            "model": candidate,
            "messages": prepared_messages,
            "stream": True,
            "system": system_prompt,
        }
        if _supports_json_format(candidate):
            request_payload["format"] = "json"
        else:
            log_event(
                "INFO",
                "chat.json_disabled",
                trace=trace_id,
                model=candidate,
            )

        try:
            response = requests.post(
                endpoint,
                json=request_payload,
                stream=True,
                timeout=120,
            )
        except requests.RequestException as exc:
            g.chat_error_class = exc.__class__.__name__
            g.chat_error_message = str(exc)
            log_event(
                "ERROR",
                "chat.error",
                trace=trace_id,
                model=candidate,
                error=g.chat_error_class,
                msg=_truncate(str(exc), _MAX_ERROR_PREVIEW),
            )
            return jsonify({"error": "upstream_unavailable", "message": str(exc), "trace_id": trace_id}), 502

        try:
            if response.status_code == 404:
                content_raw = response.text.strip() or "model not found"
                reason = _truncate(content_raw, _MAX_ERROR_PREVIEW)
                missing_reasons.append(reason)
                log_event(
                    "ERROR",
                    "chat.error",
                    trace=trace_id,
                    model=candidate,
                    code=404,
                    msg=reason,
                )
                continue

            if response.status_code >= 400:
                content_raw = response.text.strip() or f"HTTP {response.status_code}"
                g.chat_error_class = "HTTPError"
                g.chat_error_message = _truncate(content_raw, _MAX_ERROR_PREVIEW)
                log_event(
                    "ERROR",
                    "chat.error",
                    trace=trace_id,
                    model=candidate,
                    code=response.status_code,
                    msg=g.chat_error_message,
                )
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

            try:
                payload_json = _consume_streaming_response(response)
            except ValueError as exc:
                g.chat_error_class = "InvalidStream"
                g.chat_error_message = _truncate(str(exc), _MAX_ERROR_PREVIEW)
                log_event(
                    "ERROR",
                    "chat.error",
                    trace=trace_id,
                    model=candidate,
                    msg=g.chat_error_message,
                )
                return jsonify({"error": "invalid_response", "message": str(exc), "trace_id": trace_id}), 502
        finally:
            closer = getattr(response, "close", None)
            if callable(closer):
                closer()

        content = _extract_model_content(payload_json)
        reasoning_text = _extract_model_reasoning(payload_json).strip()
        try:
            structured = _coerce_schema(content)
        except ValueError as exc:
            LOGGER.debug("Falling back to raw chat content: %s", exc)
            structured = {
                "reasoning": "",
                "answer": content.strip(),
                "citations": [],
            }
            if reasoning_text:
                structured["reasoning"] = reasoning_text
        else:
            if reasoning_text and not structured.get("reasoning"):
                structured["reasoning"] = reasoning_text

        g.chat_model = candidate
        g.chat_fallback_used = attempt_index > 1
        g.chat_error_class = None
        g.chat_error_message = None

        if image_context and not image_used:
            log_event(
                "WARNING",
                "chat.vision_ignored",
                trace=trace_id,
                model=candidate,
            )

        duration_ms = int((time.perf_counter() - start) * 1000)
        log_event(
            "INFO",
            "chat.ready",
            trace=trace_id,
            model=candidate,
            fallback_used=g.chat_fallback_used,
            duration_ms=duration_ms,
        )

        response_payload = {
            "reasoning": structured["reasoning"],
            "answer": structured["answer"],
            "citations": structured["citations"],
            "model": candidate,
            "trace_id": trace_id,
        }
        flask_response = jsonify(response_payload)
        flask_response.headers["X-LLM-Model"] = candidate
        return flask_response

    tried = [name for name in attempted if name]
    hint = "ollama pull " + " or ".join(tried or [primary_model])
    combined = missing_reasons[0] if missing_reasons else hint
    g.chat_error_class = "ModelNotFound"
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


__all__ = ["bp"]
