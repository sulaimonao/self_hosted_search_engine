"""LLM chat endpoint returning structured responses from Ollama."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Iterable, Mapping, Iterator

import requests
from flask import Blueprint, Response, current_app, g, jsonify, request, stream_with_context
from pydantic import ValidationError

from server.json_logger import log_event

from ..config import AppConfig
from ..services import ollama_client
from observability import start_span
from .schemas import (
    ChatRequest,
    ChatResponsePayload,
    ChatStreamComplete,
    ChatStreamDelta,
    ChatStreamError,
    ChatStreamMetadata,
)

bp = Blueprint("chat_api", __name__, url_prefix="/api")

LOGGER = logging.getLogger(__name__)
_MAX_ERROR_PREVIEW = 500
_MAX_CONTEXT_CHARS = 8_000
_SCHEMA_PROMPT = (
    "You are a helpful assistant embedded in a self-hosted search engine. "
    "Always reply with strict JSON containing the keys reasoning, answer, and citations (an array of strings). "
    "Keep reasoning concise (<=6 sentences). Place the final user-facing reply in answer. "
    "Include citations when you reference external facts; omit when not applicable. "
    "If the knowledge cutoff prevents a confident answer, or the user explicitly grants you control of the browser "
    "to continue researching on their behalf, include an autopilot object with the shape "
    "{\"mode\": \"browser\", \"query\": <string>, \"reason\": <string>}. "
    "Only request autopilot when real-time browsing is required or the user has asked you to take over."
)
_JSON_FORMAT_ALLOWLIST: tuple[str, ...] = ()
_MODEL_ALIASES: dict[str, str] = {
    # legacy names mapped to current defaults
    "gemma:2b": "gemma3",
}


def _coerce_model(name: str | None) -> str | None:
    if not isinstance(name, str):
        return None
    normalized = name.strip()
    if not normalized:
        return None
    alias_key = normalized.lower()
    candidate = _MODEL_ALIASES.get(alias_key, normalized)

    engine_config = current_app.config.get("RAG_ENGINE_CONFIG")
    base_url = engine_config.ollama.base_url if engine_config is not None else None
    resolved = ollama_client.resolve_model_name(candidate, base_url=base_url, chat_only=True)
    return resolved or candidate


def _truncate(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    return value[: max_length - 3] + "..."


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


def _coerce_autopilot(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, Mapping):
        return None
    mode = str(payload.get("mode", "")).strip().lower()
    query = str(payload.get("query", "")).strip()
    if mode != "browser" or not query:
        return None

    reason_val = payload.get("reason")
    reason = str(reason_val).strip() if isinstance(reason_val, str) else None
    if reason == "":
        reason = None

    tools_payload = payload.get("tools")
    tools: list[dict[str, Any]] = []
    if isinstance(tools_payload, Iterable) and not isinstance(tools_payload, (str, bytes, bytearray)):
        for entry in tools_payload:
            if not isinstance(entry, Mapping):
                continue
            label = str(entry.get("label", "")).strip()
            endpoint = str(entry.get("endpoint", "")).strip()
            if not label or not endpoint:
                continue
            tool: dict[str, Any] = {"label": label, "endpoint": endpoint}
            method_val = entry.get("method")
            if isinstance(method_val, str):
                method = method_val.strip().upper()
                if method in {"GET", "POST"}:
                    tool["method"] = method
            payload_val = entry.get("payload")
            if isinstance(payload_val, Mapping):
                tool["payload"] = dict(payload_val)
            description_val = entry.get("description")
            if isinstance(description_val, str):
                description = description_val.strip()
                if description:
                    tool["description"] = description
            tools.append(tool)

    result: dict[str, Any] = {"mode": "browser", "query": query, "reason": reason}
    if tools:
        result["tools"] = tools
    return result


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

    autopilot = _coerce_autopilot(data.get("autopilot"))
    return {
        "reasoning": reasoning.strip(),
        "answer": answer.strip(),
        "citations": citations_list,
        "autopilot": autopilot,
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
    client_timezone: str | None = None,
    server_time: str | None = None,
    server_timezone: str | None = None,
    server_time_utc: str | None = None,
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
    time_bits: list[str] = []
    if server_time:
        label = server_timezone or "server-local"
        time_bits.append(f"Server time ({label}): {server_time}")
    if server_time_utc:
        time_bits.append(f"Server time (UTC): {server_time_utc}")
    if client_timezone:
        time_bits.append(f"Client timezone: {client_timezone}")
    if time_bits:
        system_sections.append("Time context:\n" + "\n".join(time_bits))
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


def _close_response_safely(response: Any) -> None:
    """Best-effort wrapper to close streaming responses."""

    close_fn = getattr(response, "close", None)
    if callable(close_fn):
        try:
            close_fn()
        except Exception:  # pragma: no cover - defensive cleanup
            LOGGER.debug("failed to close chat response", exc_info=True)


class _StreamAccumulator:
    """Track the latest streaming payload and accumulated text."""

    def __init__(self) -> None:
        self.payload: Mapping[str, Any] | None = None
        self.answer: str = ""
        self.reasoning: str = ""

    def update(self, chunk: Mapping[str, Any]) -> ChatStreamDelta | None:
        message = chunk.get("message")
        if not isinstance(message, Mapping):
            return None
        delta = ChatStreamDelta()
        content = message.get("content")
        if isinstance(content, str):
            trimmed = content.strip()
            if trimmed:
                previous_answer = self.answer
                if trimmed != previous_answer:
                    self.answer = trimmed
                    delta.answer = self.answer
                    if trimmed.startswith(previous_answer):
                        appended = trimmed[len(previous_answer) :]
                    else:
                        appended = self.answer
                    if appended:
                        delta.delta = appended
        reasoning_value = None
        for key in ("reasoning", "thinking"):
            raw = message.get(key)
            if isinstance(raw, str) and raw.strip():
                reasoning_value = raw.strip()
                break
        if reasoning_value and reasoning_value != self.reasoning:
            self.reasoning = reasoning_value
            delta.reasoning = self.reasoning
        if delta.answer is None and delta.reasoning is None and delta.delta is None:
            return None
        self.payload = chunk
        return delta


def _iter_streaming_response(
    response: requests.Response,
) -> Iterator[tuple[Mapping[str, Any], ChatStreamDelta, "_StreamAccumulator", str]]:
    """Yield incremental updates for a streaming Ollama response."""

    accumulator = _StreamAccumulator()
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
        delta = accumulator.update(payload)
        if delta is not None:
            yield payload, delta, accumulator, decoded



def _drain_chat_response(response: requests.Response) -> tuple[Mapping[str, Any], _StreamAccumulator]:
    """Consume the streaming response and return the final payload + accumulator."""

    accumulator: _StreamAccumulator | None = None
    final_payload: Mapping[str, Any] | None = None
    for payload, _delta, acc, _raw in _iter_streaming_response(response):
        accumulator = acc
        final_payload = payload
    _close_response_safely(response)
    if accumulator is None or accumulator.payload is None or final_payload is None:
        raise ValueError("Upstream response stream was empty")
    return accumulator.payload, accumulator


def _serialize_event(event: ChatStreamMetadata | ChatStreamDelta | ChatStreamComplete | ChatStreamError) -> bytes:
    if hasattr(event, "model_dump"):
        payload = event.model_dump(exclude_none=True)  # type: ignore[attr-defined]
    else:  # pragma: no cover - defensive fallback
        payload = event  # type: ignore[assignment]
    return (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")


def _ndjson_stream(events: Iterable[ChatStreamMetadata | ChatStreamDelta | ChatStreamComplete | ChatStreamError]) -> Iterator[bytes]:
    for event in events:
        yield _serialize_event(event)


def _sse_frame(event: str | None, payload: Mapping[str, Any]) -> bytes:
    prefix = f"event: {event}\n" if event else ""
    body = json.dumps(payload, ensure_ascii=False)
    return f"{prefix}data: {body}\n\n".encode("utf-8")


def _sse_stream(events: Iterable[ChatStreamMetadata | ChatStreamDelta | ChatStreamComplete | ChatStreamError]) -> Iterator[bytes]:
    for event in events:
        if isinstance(event, ChatStreamMetadata):
            data = event.model_dump(exclude_none=True)
            data.pop("type", None)
            yield _sse_frame("metadata", data)
        elif isinstance(event, ChatStreamDelta):
            data = event.model_dump(exclude_none=True)
            data.pop("type", None)
            if "delta" not in data and event.answer is not None:
                data.setdefault("delta", event.answer)
            yield _sse_frame("delta", data)
        elif isinstance(event, ChatStreamComplete):
            payload = event.payload.model_dump(exclude_none=True)
            yield _sse_frame("complete", {"payload": payload})
        elif isinstance(event, ChatStreamError):
            data = event.model_dump(exclude_none=True)
            data.pop("type", None)
            yield _sse_frame("error", data)


def _render_response_payload(
    *,
    candidate: str,
    payload_json: Mapping[str, Any],
    accumulator: _StreamAccumulator,
    trace_id: str | None,
    attempt_index: int,
    start_time: float,
    chat_span: Any,
    image_context: str | None,
    image_used: bool,
) -> ChatResponsePayload:
    content = _extract_model_content(payload_json)
    reasoning_text = _extract_model_reasoning(payload_json).strip()
    try:
        structured = _coerce_schema(content)
    except ValueError as exc:  # pragma: no cover - repair attempts best effort
        LOGGER.debug("Falling back to raw chat content: %s", exc)
        structured = {
            "reasoning": reasoning_text or accumulator.reasoning or "",
            "answer": content.strip() or accumulator.answer or "",
            "citations": [],
        }
    else:
        if reasoning_text and not structured.get("reasoning"):
            structured["reasoning"] = reasoning_text
    if accumulator.reasoning and not structured.get("reasoning"):
        structured["reasoning"] = accumulator.reasoning
    if accumulator.answer and not structured.get("answer"):
        structured["answer"] = accumulator.answer
    citations = structured.get("citations") or []
    if not isinstance(citations, list):
        citations = []
    response_payload = ChatResponsePayload(
        reasoning=(structured.get("reasoning") or "").strip(),
        answer=(structured.get("answer") or "").strip(),
        citations=[str(item) for item in citations if isinstance(item, (str, int, float))],
        model=candidate,
        trace_id=trace_id,
        autopilot=structured.get("autopilot"),
    )
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
    duration_ms = int((time.perf_counter() - start_time) * 1000)
    log_event(
        "INFO",
        "chat.ready",
        trace=trace_id,
        model=candidate,
        fallback_used=bool(g.chat_fallback_used),
        duration_ms=duration_ms,
    )
    if chat_span is not None:
        chat_span.set_attribute("chat.success_model", candidate)
        chat_span.set_attribute("chat.duration_ms", duration_ms)
        chat_span.set_attribute("chat.fallback_used", bool(g.chat_fallback_used))
    return response_payload


def _stream_chat_response(
    *,
    candidate: str,
    attempt_index: int,
    response: requests.Response,
    trace_id: str | None,
    request_id: str | None,
    streaming_start: float,
    chat_span: Any,
    image_context: str | None,
    image_used: bool,
    transport: str,
) -> Response:
    metadata = ChatStreamMetadata(
        attempt=attempt_index,
        model=candidate,
        trace_id=trace_id,
        request_id=request_id,
    )
    chunk_samples: list[str] = []
    frame_count = 0
    end_reason = "unknown"

    def _events() -> Iterable[ChatStreamMetadata | ChatStreamDelta | ChatStreamComplete | ChatStreamError]:
        nonlocal frame_count, end_reason
        yield metadata
        accumulator: _StreamAccumulator | None = None
        try:
            for payload, delta, acc, raw in _iter_streaming_response(response):
                accumulator = acc
                if raw and len(chunk_samples) < 3:
                    chunk_samples.append(raw[:80])
                frame_count += 1
                yield delta
            if accumulator is None or accumulator.payload is None:
                raise ValueError("Upstream response stream was empty")
            payload_model = _render_response_payload(
                candidate=candidate,
                payload_json=accumulator.payload,
                accumulator=accumulator,
                trace_id=trace_id,
                attempt_index=attempt_index,
                start_time=streaming_start,
                chat_span=chat_span,
                image_context=image_context,
                image_used=image_used,
            )
            end_reason = "complete"
            yield ChatStreamComplete(payload=payload_model)
        except Exception as exc:  # pragma: no cover - defensive streaming guard
            g.chat_error_class = exc.__class__.__name__
            g.chat_error_message = str(exc)
            log_event(
                "ERROR",
                "chat.error",
                trace=trace_id,
                model=candidate,
                request_id=request_id,
                transport=transport,
                attempt=attempt_index,
                msg=_truncate(str(exc), _MAX_ERROR_PREVIEW),
            )
            if chat_span is not None:
                chat_span.set_attribute("chat.success", False)
            end_reason = "error"
            yield ChatStreamError(
                error="stream_error",
                hint="upstream response terminated unexpectedly",
                trace_id=trace_id,
            )
        finally:
            log_event(
                "INFO",
                "chat.stream_summary",
                trace=trace_id,
                model=candidate,
                request_id=request_id,
                transport=transport,
                frame_count=frame_count,
                chunks=chunk_samples,
                end=end_reason,
            )
            _close_response_safely(response)

    if transport == "sse":
        resp = Response(stream_with_context(_sse_stream(_events())), mimetype="text/event-stream")
        resp.headers.setdefault("Cache-Control", "no-store, no-transform")
    else:
        resp = Response(stream_with_context(_ndjson_stream(_events())), mimetype="application/x-ndjson")
        resp.headers.setdefault("Cache-Control", "no-store")
    resp.headers["X-LLM-Model"] = candidate
    resp.headers.setdefault("X-Accel-Buffering", "no")
    resp.headers.setdefault("X-Stream-Transport", transport)
    return resp


def _handle_chat_request(
    chat_request: ChatRequest,
    *,
    streaming_requested: bool,
    preferred_transport: str,
    route: str,
) -> Response:
    sanitized_messages = [msg.model_dump(exclude_none=True) for msg in chat_request.messages]

    chat_logger = current_app.config.get("CHAT_LOGGER")
    if hasattr(chat_logger, "info"):
        preview = " | ".join(entry.get("content", "") for entry in sanitized_messages)
        chat_logger.info("chat request received: %s", preview.strip())

    requested_model = chat_request.model
    url_value = chat_request.url
    text_context = chat_request.text_context
    image_context = chat_request.image_context
    client_timezone = chat_request.client_timezone
    server_time = chat_request.server_time
    server_timezone = chat_request.server_timezone
    server_time_utc = chat_request.server_time_utc
    request_id = chat_request.request_id

    if request_id:
        setattr(g, "chat_request_id", request_id)

    trace_id = getattr(g, "trace_id", None)
    primary_model, fallback_model, _ = _configured_models()

    trace_inputs = {
        "message_count": len(sanitized_messages),
        "requested_model": requested_model,
        "has_context": bool(text_context or image_context),
        "request_id": request_id,
    }

    with start_span(
        "http.chat",
        attributes={"http.route": route, "http.method": request.method},
        inputs=trace_inputs,
    ) as chat_span:
        candidates: list[str] = []
        if requested_model:
            candidates.append(requested_model)
        else:
            candidates.append(primary_model)
            if fallback_model and fallback_model != primary_model:
                candidates.append(fallback_model)

        candidate_pairs: list[tuple[str | None, str]] = []
        seen_models: set[str] = set()
        for candidate in candidates:
            resolved = _coerce_model(candidate) or ""
            key = resolved.strip().lower()
            if not key:
                continue
            if key in seen_models:
                continue
            seen_models.add(key)
            candidate_pairs.append((candidate, resolved))

        if chat_span is not None:
            chat_span.set_attribute("chat.candidate_count", len(candidate_pairs))

        config: AppConfig = current_app.config["APP_CONFIG"]
        endpoint = _chat_endpoint(config)

        attempted: list[str] = []
        missing_reasons: list[str] = []

        for attempt_index, (alias_label, candidate) in enumerate(
            candidate_pairs, start=1
        ):
            attempted.append(candidate)
            prepared_messages, image_used, system_prompt = _prepare_messages(
                candidate=candidate,
                base_messages=sanitized_messages,
                url=url_value,
                text_context=text_context,
                image_context=image_context,
                client_timezone=client_timezone,
                server_time=server_time,
                server_timezone=server_timezone,
                server_time_utc=server_time_utc,
            )

            log_event(
                "INFO",
                "chat.request",
                trace=trace_id,
                model=candidate,
                request_id=request_id,
                alias=alias_label if alias_label and alias_label != candidate else None,
                attempt=attempt_index,
                url=url_value,
                context_chars=(len(text_context) if isinstance(text_context, str) else 0),
                prompt_chars=sum(len(item.get("content", "")) for item in prepared_messages),
            )

            if chat_span is not None:
                chat_span.set_attribute("chat.attempt", attempt_index)

            request_payload = {"model": candidate, "messages": prepared_messages}
            if system_prompt:
                request_payload["system"] = system_prompt
            if image_context:
                request_payload["images"] = [image_context]
            if _supports_json_format(candidate):
                request_payload["format"] = "json"
            else:
                log_event(
                    "INFO",
                    "chat.json_disabled",
                    trace=trace_id,
                    model=candidate,
                    request_id=request_id,
                )

            response = None
            attempt_start = time.perf_counter()
            try:
                with start_span(
                    "llm.chat",
                    attributes={"llm.model": candidate, "llm.attempt": attempt_index},
                    inputs={
                        "message_count": len(prepared_messages),
                        "has_image": bool(image_used),
                    },
                ) as llm_span:
                    response = requests.post(
                        endpoint,
                        json=request_payload,
                        stream=bool(streaming_requested),
                        timeout=120,
                    )
                    if llm_span is not None:
                        llm_span.set_attribute("http.status_code", response.status_code)
                        llm_span.set_attribute("llm.json_format", "format" in request_payload)
            except requests.RequestException as exc:
                g.chat_error_class = exc.__class__.__name__
                g.chat_error_message = str(exc)
                log_event(
                    "ERROR",
                    "chat.error",
                    trace=trace_id,
                    model=candidate,
                    request_id=request_id,
                    attempt=attempt_index,
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

            if response is None:  # pragma: no cover - defensive guard
                continue

            if response.status_code == 404:
                content_raw = response.text.strip() or "model not found"
                reason = _truncate(content_raw, _MAX_ERROR_PREVIEW)
                missing_reasons.append(reason)
                log_event(
                    "ERROR",
                    "chat.error",
                    trace=trace_id,
                    model=candidate,
                    request_id=request_id,
                    code=404,
                    msg=reason,
                )
                response.close()
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
                    request_id=request_id,
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

            if streaming_requested:
                transport = "sse" if preferred_transport == "sse" else "ndjson"
                return _stream_chat_response(
                    candidate=candidate,
                    attempt_index=attempt_index,
                    response=response,
                    trace_id=trace_id,
                    request_id=request_id,
                    streaming_start=attempt_start,
                    chat_span=chat_span,
                    image_context=image_context,
                    image_used=image_used,
                    transport=transport,
                )

            try:
                payload_json = response.json()
            except ValueError as exc:
                g.chat_error_class = "InvalidResponse"
                g.chat_error_message = _truncate(str(exc), _MAX_ERROR_PREVIEW)
                log_event(
                    "ERROR",
                    "chat.error",
                    trace=trace_id,
                    model=candidate,
                    request_id=request_id,
                    msg=g.chat_error_message,
                )
                return (
                    jsonify(
                        {
                            "error": "invalid_response",
                            "message": str(exc),
                            "trace_id": trace_id,
                        }
                    ),
                    502,
                )

            if not isinstance(payload_json, Mapping):
                g.chat_error_class = "InvalidResponse"
                g.chat_error_message = "upstream response missing JSON object"
                log_event(
                    "ERROR",
                    "chat.error",
                    trace=trace_id,
                    model=candidate,
                    msg=g.chat_error_message,
                )
                return (
                    jsonify(
                        {
                            "error": "invalid_response",
                            "message": g.chat_error_message,
                            "trace_id": trace_id,
                        }
                    ),
                    502,
                )

            accumulator = _StreamAccumulator()
            if accumulator.update(payload_json) is None:
                accumulator.payload = payload_json

            response_payload = _render_response_payload(
                candidate=candidate,
                payload_json=payload_json,
                accumulator=accumulator,
                trace_id=trace_id,
                attempt_index=attempt_index,
                start_time=attempt_start,
                chat_span=chat_span,
                image_context=image_context,
                image_used=image_used,
            )

            flask_response = jsonify(response_payload.model_dump(exclude_none=True))
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
        if chat_span is not None:
            chat_span.set_attribute("chat.success", False)
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

@bp.post("/chat")
def chat_invoke() -> Response:
    try:
        chat_request = ChatRequest.model_validate(request.get_json(silent=True) or {})
    except ValidationError as exc:
        g.chat_error_class = "ValidationError"
        g.chat_error_message = "invalid_request"
        return (
            jsonify(
                {
                    "error": "validation_error",
                    "detail": exc.errors(),
                    "trace_id": getattr(g, "trace_id", None),
                }
            ),
            400,
        )

    accept_header = (request.headers.get("Accept") or "").lower()
    stream_flag = request.args.get("stream")
    if chat_request.stream is not None:
        streaming_requested = bool(chat_request.stream)
    elif stream_flag is not None:
        streaming_requested = stream_flag.strip().lower() not in {"0", "false", "no", "off"}
    else:
        streaming_requested = "application/json" not in accept_header

    preferred_transport = "ndjson" if streaming_requested else "json"
    return _handle_chat_request(
        chat_request,
        streaming_requested=streaming_requested,
        preferred_transport=preferred_transport,
        route="/api/chat",
    )

@bp.post("/chat/stream")
def chat_stream_invoke() -> Response:
    try:
        chat_request = ChatRequest.model_validate(request.get_json(silent=True) or {})
    except ValidationError as exc:
        g.chat_error_class = "ValidationError"
        g.chat_error_message = "invalid_request"
        return (
            jsonify(
                {
                    "error": "validation_error",
                    "detail": exc.errors(),
                    "trace_id": getattr(g, "trace_id", None),
                }
            ),
            400,
        )

    return _handle_chat_request(
        chat_request,
        streaming_requested=True,
        preferred_transport="sse",
        route="/api/chat/stream",
    )

