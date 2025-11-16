"""LLM chat endpoint returning structured responses from Ollama."""

from __future__ import annotations

import json
import logging
import re
import threading
import time
import uuid
from typing import Any, Dict, Iterable, Iterator, List, Literal, Mapping, Optional, Sequence, Union

import requests
from flask import Blueprint, Response, current_app, g, jsonify, request, stream_with_context
from pydantic import ValidationError
from uuid import uuid4

from server.json_logger import log_event

from backend.app.db import AppStateDB
from backend.app.io import (
    allowed_model_aliases,
    chat_schema as io_chat_schema,
    normalize_model_alias,
)
from backend.app.services.progress_bus import ProgressBus
from backend.app.services.incident_log import IncidentLog
from backend.app.services.vector_index import EmbedderUnavailableError, VectorIndexService

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
_DIAGNOSTIC_JOB_ID = "__diagnostics__"
_SCHEMA_PROMPT = (
    "You are a helpful assistant embedded in a self-hosted search engine. "
    "Always reply with strict JSON containing the keys reasoning, answer, and citations (an array of strings). "
    "Keep reasoning concise (<=6 sentences). Place the final user-facing reply in the answer field; never rely on message for presentation. "
    "Include citations when you reference external facts; omit when not applicable. "
    "If additional automation could help (e.g., browsing, searching, file retrieval, running code), include an autopilot object with the shape "
    '{"mode": "browser" | "tools" | "multi", "query"?: string, "reason"?: string, "steps"?: Verb[], "tools"?: AutopilotTool[]}. '
    "Use directive steps for browser interactions and describe API-capable helpers in the tools array (e.g., search_vector, file_search.msearch, python_user_visible, browser.search). "
    "Only request autopilot when real-time actions are necessary or the user has given consent. "
    "Available helper tools: diagnostics.run (POST /api/diagnostics/run, payload {smoke?: boolean}), index.snapshot (POST /api/index/snapshot, payload {url}), "
    "index.site (POST /api/index/site, payload {url, scope}), and db.query (POST /api/db/query, payload {sql} or {named_query}). "
    "Request db.query only when the context prelude indicates DB access is enabled; diagnostics.run may always be requested."
)
_JSON_FORMAT_ALLOWLIST: tuple[str, ...] = ()
_EMPTY_RESPONSE_FALLBACK = "No data retrieved, but model responded successfully."
_TEXTUAL_CONTENT_PATTERN = re.compile(r"[A-Za-z]")
_MISSING_TEXT_FALLBACK = "I’m here, but I didn’t receive usable text from the model."
_INCIDENT_DUPLICATE_SSE = "DUPLICATE_SSE"

_TOOL_REGISTRY: dict[str, dict[str, str]] = {
    "diagnostics.run": {"method": "POST", "endpoint": "/api/diagnostics/run"},
    "index.snapshot": {"method": "POST", "endpoint": "/api/index/snapshot"},
    "index.site": {"method": "POST", "endpoint": "/api/index/site"},
    "db.query": {"method": "POST", "endpoint": "/api/db/query"},
    "embeddings.add": {"method": "POST", "endpoint": "/api/embeddings/build"},
}


class _SseRegistry:
    """Track active SSE request identifiers to enforce single-flight semantics."""

    def __init__(self, ttl_seconds: float = 120.0) -> None:
        self._ttl = ttl_seconds
        self._entries: Dict[str, float] = {}
        self._lock = threading.Lock()

    def _prune(self, now: float) -> None:
        expired = [key for key, ts in self._entries.items() if now - ts > self._ttl]
        for key in expired:
            self._entries.pop(key, None)

    def claim(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            self._prune(now)
            if key in self._entries:
                return False
            self._entries[key] = now
            return True

    def release(self, key: str) -> None:
        with self._lock:
            self._entries.pop(key, None)


_SSE_REGISTRY = _SseRegistry(ttl_seconds=120.0)


def _state_db() -> AppStateDB | None:
    try:
        state_db = current_app.config.get("APP_STATE_DB")
    except RuntimeError:  # pragma: no cover - outside request context
        return None
    if isinstance(state_db, AppStateDB):
        return state_db
    return None


def _ensure_thread_context(chat_request: ChatRequest) -> str:
    preferred = chat_request.chat_id
    state_db = _state_db()
    tab_id = chat_request.tab_id
    if not preferred and state_db is not None and tab_id:
        tab_thread = state_db.tab_thread_id(tab_id)
        if tab_thread:
            preferred = tab_thread
    if not preferred:
        context = chat_request.context or {}
        context_thread = context.get("thread_id") if isinstance(context, Mapping) else None
        if isinstance(context_thread, str) and context_thread.strip():
            preferred = context_thread.strip()
    if not preferred:
        preferred = chat_request.request_id or uuid4().hex
    if state_db is not None:
        state_db.ensure_llm_thread(preferred, origin="chat")
        if tab_id:
            state_db.bind_tab_thread(tab_id, preferred)
    g.chat_thread_id = preferred
    return preferred


def _incident_log() -> IncidentLog | None:
    try:
        log = current_app.config.get("INCIDENT_LOG")
    except RuntimeError:  # pragma: no cover - outside request context
        return None
    if isinstance(log, IncidentLog):
        return log
    return None


def _record_incident(kind: str, *, message: str | None = None, detail: dict[str, Any] | None = None) -> None:
    log = _incident_log()
    if log is None:
        return
    log.record(kind, message=message, detail=detail or {})


@bp.get("/chat/schema")
def chat_schema_echo() -> Response:
    """Expose the normalized chat schemas for diagnostics and tooling."""

    return jsonify(io_chat_schema())


def _looks_like_json(text: str) -> bool:
    stripped = text.lstrip()
    if not stripped:
        return False
    if stripped.startswith("{") or stripped.startswith("["):
        return True
    return "```json" in text.lower()


def _guard_contentful_text(candidate: str, *, fallback: str | None = None) -> str:
    text = (candidate or "").strip()
    if len(text) >= 4 and _TEXTUAL_CONTENT_PATTERN.search(text):
        return text
    fallback_text = (fallback or "").strip()
    if len(fallback_text) >= 4 and _TEXTUAL_CONTENT_PATTERN.search(fallback_text):
        return fallback_text
    return _MISSING_TEXT_FALLBACK


def _shrink_payload(value: Any, *, max_string: int = 512, max_items: int = 20) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _shrink_payload(item, max_string=max_string, max_items=max_items)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [
            _shrink_payload(item, max_string=max_string, max_items=max_items)
            for item in list(value)[:max_items]
        ]
    if isinstance(value, str):
        text = value
        if len(text) > max_string:
            return text[: max_string - 3] + "..."
        return text
    return value


def _payload_preview(payload: Any, *, limit: int = 900) -> str:
    try:
        rendered = json.dumps(payload, ensure_ascii=False)
    except (TypeError, ValueError):
        rendered = str(payload)
    if len(rendered) > limit:
        return rendered[: limit - 3] + "..."
    return rendered


def _publish_payload(stage: str, payload: Any) -> None:
    try:
        bus = current_app.config.get("PROGRESS_BUS")
    except RuntimeError:
        bus = None
    if not isinstance(bus, ProgressBus):
        return
    event = {
        "stage": stage,
        "kind": "payload",
        "message": _payload_preview(payload),
        "payload": _shrink_payload(payload),
        "ts": time.time(),
    }
    try:
        bus.publish(_DIAGNOSTIC_JOB_ID, event)
    except Exception:  # pragma: no cover - diagnostics best effort
        LOGGER.debug("diagnostics payload publish failed", exc_info=True)


_MIN_PAGE_CONTEXT_CHARS = 160


def _indent_block(text: str, prefix: str = "  ") -> str:
    lines = (text or "").splitlines() or [""]
    return "\n".join(f"{prefix}{line}" for line in lines)


def _render_context_prelude(
    context: Mapping[str, Any] | None,
    tools: Sequence[Mapping[str, Any]] | None = None,
) -> tuple[str, dict[str, Any]]:
    payload = context if isinstance(context, Mapping) else {}
    meta: dict[str, Any] = {}

    tool_lines: list[str] = ["[TOOLS]"]
    declared_tools: list[str] = []
    if tools:
        for entry in tools:
            if not isinstance(entry, Mapping):
                continue
            name = str(entry.get("name") or "").strip()
            if not name:
                continue
            description = str(entry.get("description") or "").strip()
            schema = entry.get("input_schema") if isinstance(entry, Mapping) else None
            if not declared_tools:
                tool_lines.append(
                    "You MAY call one tool at a time by returning strict JSON like "
                    '{"tool_call":{"name":"<tool>","arguments":{...}},"answer":"<your natural language answer>"}.'
                )
                tool_lines.append("Available tools:")
            line = f"- {name}"
            if description:
                line += f" — {description}"
            tool_lines.append(line)
            if isinstance(schema, Mapping) and schema:
                try:
                    schema_json = json.dumps(schema, ensure_ascii=False)
                except Exception:
                    schema_json = str(schema)
                tool_lines.append(f"  schema: {schema_json}")
            declared_tools.append(name)
    if not declared_tools:
        tool_lines.append("No tools declared for this turn.")
    tool_lines.append("[/TOOLS]")
    meta["tool_count"] = len(declared_tools)
    if declared_tools:
        meta["tools"] = declared_tools

    lines: list[str] = tool_lines + ["[CONTEXT]"]

    page = payload.get("page") if isinstance(payload, Mapping) else None
    page_title = ""
    page_url = ""
    page_text = ""
    if isinstance(page, Mapping):
        page_title = str(page.get("title") or "").strip()
        page_url = str(page.get("url") or "").strip()
        text_value = page.get("text")
        if isinstance(text_value, str):
            page_text = text_value[: _MAX_CONTEXT_CHARS].strip()
    if page_title or page_url:
        lines.append(f"- Page: {page_title or 'Untitled'} ({page_url or 'unknown'})")
    else:
        lines.append("- Page: not attached")
    if page_text:
        lines.append("  <<BEGIN PAGE TEXT>>")
        lines.append(_indent_block(page_text, "    "))
        lines.append("  <<END PAGE TEXT>>")
        meta["page_chars"] = len(page_text)
    if page_url:
        meta["page_url"] = page_url

    diagnostics = payload.get("diagnostics") if isinstance(payload, Mapping) else None
    diag_status = "unknown"
    if isinstance(diagnostics, Mapping):
        diag_status = str(diagnostics.get("status") or "unknown").strip() or "unknown"
        diag_summary_text = str(diagnostics.get("summary") or "").strip()
        diag_summary = diag_summary_text or "No summary provided"
        checks = diagnostics.get("checks")
        criticals: list[str] = []
        if isinstance(checks, Iterable):
            for entry in checks:
                if not isinstance(entry, Mapping):
                    continue
                is_critical = bool(entry.get("critical"))
                status_value = str(entry.get("status") or "").strip().lower()
                if status_value in {"error", "fail", "critical"}:
                    is_critical = True
                if not is_critical:
                    continue
                label = str(entry.get("id") or entry.get("title") or entry.get("detail") or "critical").strip()
                if label:
                    criticals.append(label)
        critical_text = ", ".join(criticals[:4]) if criticals else "none"
        diag_summary = f"{diag_status}: {diag_summary}"
        lines.append(f"- Diagnostics summary: {diag_status}; criticals: {critical_text}")
        meta["diagnostics_status"] = diag_status
    else:
        lines.append("- Diagnostics summary: none attached")

    db_payload = payload.get("db") if isinstance(payload, Mapping) else None
    db_enabled = bool(db_payload.get("enabled")) if isinstance(db_payload, Mapping) else False
    lines.append(f"- DB access: {'enabled' if db_enabled else 'disabled'}")
    meta["db_enabled"] = db_enabled

    tools_payload = payload.get("tools") if isinstance(payload, Mapping) else None
    allow_indexing = bool(tools_payload.get("allowIndexing")) if isinstance(tools_payload, Mapping) else False
    lines.append(
        "- Tools allowed: diagnostics.run (always on), index.snapshot/index.site: "
        f"{'enabled' if allow_indexing else 'disabled'}, db.query: {'enabled' if db_enabled else 'disabled'}"
    )
    meta["tools_indexing"] = allow_indexing

    lines.append("[/CONTEXT]")
    return "\n".join(lines), meta


def _maybe_index_page_context(context: Mapping[str, Any] | None) -> None:
    if not isinstance(context, Mapping):
        return
    page = context.get("page")
    if not isinstance(page, Mapping):
        return
    text_value = page.get("text")
    if not isinstance(text_value, str):
        return
    cleaned = text_value.strip()
    if len(cleaned) < _MIN_PAGE_CONTEXT_CHARS:
        return
    app = current_app._get_current_object()

    payload = {
        "text": cleaned,
        "url": str(page.get("url") or "").strip() or None,
        "title": str(page.get("title") or "").strip() or None,
    }

    def _runner(app_ctx, page_payload):
        with app_ctx.app_context():
            service = current_app.config.get("VECTOR_INDEX_SERVICE")
            if not isinstance(service, VectorIndexService):
                return
            metadata = {"source": "chat_context"}
            try:
                service.upsert_document(
                    text=page_payload["text"],
                    url=page_payload.get("url"),
                    title=page_payload.get("title"),
                    metadata=metadata,
                )
            except EmbedderUnavailableError as exc:
                LOGGER.debug("context embedding unavailable: %s", exc.detail)
            except Exception:
                LOGGER.debug("context embedding failed", exc_info=True)

    try:
        threading.Thread(
            target=_runner,
            args=(app, payload),
            name="chat-context-embed",
            daemon=True,
        ).start()
    except Exception:  # pragma: no cover - background scheduling best effort
        LOGGER.debug("failed to schedule context embedding", exc_info=True)


def _normalize_tool_arguments(payload: Any) -> dict[str, Any]:
    if isinstance(payload, Mapping):
        return {str(key): value for key, value in payload.items()}
    return {}


def _execute_tool_call(name: str, arguments: Mapping[str, Any] | None) -> tuple[bool, Any, int]:
    spec = _TOOL_REGISTRY.get(name)
    if not spec:
        return False, {"error": "unknown_tool"}, 0
    method = spec.get("method", "POST").upper()
    endpoint = spec.get("endpoint") or ""
    if not endpoint:
        return False, {"error": "unconfigured_tool"}, 0
    data = _normalize_tool_arguments(arguments)
    app = current_app._get_current_object()
    with app.test_client() as client:
        if method == "GET":
            response = client.get(endpoint, query_string=data)
        else:
            response = client.post(endpoint, json=data)
    try:
        result_payload = response.get_json(silent=True)
    except Exception:  # pragma: no cover - defensive
        result_payload = None
    if result_payload is None:
        body_text = response.get_data(as_text=True)
        result_payload = body_text.strip() if body_text else None
    success = response.status_code < 400
    return success, result_payload, response.status_code


def _format_tool_append(name: str, success: bool, result: Any) -> str:
    label = "TOOL RESULT" if success else "TOOL ERROR"
    if isinstance(result, (dict, list)):
        try:
            rendered = json.dumps(result, ensure_ascii=False, indent=2)
        except Exception:
            rendered = _payload_preview(result, limit=600)
        return f"[{label}: {name}]\n```json\n{rendered}\n```"
    text = str(result or "").strip()
    if not text:
        text = "OK" if success else "No details provided"
    return f"[{label}: {name}]\n{text}"


def _coerce_schema(resp: Union[str, Dict[str, Any], List[Any], None]) -> Dict[str, Any]:
    """Normalize model/tool output into a consistent schema."""

    if resp is None:
        return {"message": ""}

    if isinstance(resp, str):
        return {"message": resp.strip()}

    if isinstance(resp, list):
        if not resp:
            return {"message": "No data retrieved, but the model responded."}
        combined = " ".join(str(item) for item in resp).strip()
        return {"message": combined or "No data retrieved, but the model responded."}

    if isinstance(resp, Mapping):
        data = dict(resp)
        message = ""
        raw_message = data.get("message")
        if isinstance(raw_message, str) and raw_message.strip():
            message = raw_message.strip()
        else:
            for key in ("answer", "output", "text", "content"):
                value = data.get(key)
                if isinstance(value, str) and value.strip():
                    message = value.strip()
                    break
        if not message:
            message = str(resp).strip()
        data["message"] = message
        return data

    return {"message": str(resp).strip()}


def _truncate(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    return value[: max_length - 3] + "..."


def _configured_models() -> tuple[str, str | None, str | None]:
    engine_config = current_app.config.get("RAG_ENGINE_CONFIG")
    primary_alias = normalize_model_alias(None)
    fallback_alias: str | None = None
    embed_alias: str | None = "embeddinggemma:latest"
    if engine_config is not None:
        raw_primary = getattr(engine_config.models, "llm_primary", None)
        try:
            primary_alias = normalize_model_alias(raw_primary or primary_alias)
        except ValueError:
            primary_alias = normalize_model_alias(None)
        raw_fallback = getattr(engine_config.models, "llm_fallback", None)
        if isinstance(raw_fallback, str) and raw_fallback.strip():
            try:
                fallback_alias = normalize_model_alias(raw_fallback)
            except ValueError:
                fallback_alias = None
        raw_embed = getattr(engine_config.models, "embed", None)
        if isinstance(raw_embed, str) and raw_embed.strip():
            embed_alias = raw_embed.strip()
    return primary_alias, fallback_alias, embed_alias


def _supports_json_format(model: str) -> bool:
    normalized = (model or "").lower()
    return any(normalized.startswith(prefix) for prefix in _JSON_FORMAT_ALLOWLIST)


def _first_string_value(value: Any) -> str:
    if isinstance(value, str) and value:
        if value.strip():
            return value
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


def _stringify_iterable(items: Iterable[Any]) -> str:
    parts: list[str] = []
    for entry in items:
        if isinstance(entry, str):
            candidate = entry.strip()
        elif isinstance(entry, Mapping):
            try:
                candidate = json.dumps(entry, ensure_ascii=False)
            except TypeError:
                candidate = str(entry)
        else:
            candidate = str(entry).strip()
        if candidate:
            parts.append(candidate)
    return " ".join(parts).strip()


def _iterable_schema_fallback(items: Iterable[Any]) -> dict[str, Any]:
    message = _stringify_iterable(items) or _EMPTY_RESPONSE_FALLBACK
    return {
        "reasoning": "",
        "answer": message,
        "citations": [],
    }


def _coerce_message_text(value: Any) -> str:
    """Flatten structured Ollama chat message content to plain text while preserving spacing."""

    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        text_val = value.get("text")
        if isinstance(text_val, str):
            return text_val
        nested = value.get("content")
        if nested is not None and nested is not value:
            return _coerce_message_text(nested)
        return ""
    if isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray)):
        return "".join(
            text
            for entry in value
            for text in [_coerce_message_text(entry)]
            if text
        )
    return ""


def _coerce_autopilot(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, Mapping):
        return None
    mode = str(payload.get("mode", "browser") or "").strip().lower()
    if mode not in {"browser", "tools", "multi"}:
        return None

    query_val = payload.get("query")
    query = str(query_val).strip() if isinstance(query_val, str) else ""
    reason_val = payload.get("reason")
    reason = str(reason_val).strip() if isinstance(reason_val, str) else ""
    directive_value = payload.get("directive")
    directive = dict(directive_value) if isinstance(directive_value, Mapping) else None
    steps_value = payload.get("steps")
    steps: list[Any] | None = None
    if isinstance(steps_value, Iterable) and not isinstance(steps_value, (str, bytes, bytearray)):
        steps = list(steps_value)

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

    if not any([query, reason, directive, steps, tools]):
        return None

    result: dict[str, Any] = {"mode": mode}
    if query:
        result["query"] = query
    # Always include reason key to ensure stable schema for clients/tests
    if isinstance(reason, str) and reason.strip():
        result["reason"] = reason
    else:
        result["reason"] = None
    if directive:
        result["directive"] = directive
    if steps:
        result["steps"] = steps
    if tools:
        result["tools"] = tools
    return result


def _coerce_model_schema(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        data = dict(value)
    elif isinstance(value, Iterable) and not isinstance(value, (str, bytes, bytearray)):
        return _iterable_schema_fallback(value)
    else:
        candidate = _strip_code_fence(str(value))
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError as exc:  # pragma: no cover - repair attempts best effort
            start = candidate.find("{")
            end = candidate.rfind("}")
            if start != -1 and end != -1 and end > start:
                snippet = candidate[start : end + 1]
                try:
                    parsed = json.loads(snippet)
                except json.JSONDecodeError as second_exc:  # pragma: no cover - best effort repair
                    raise ValueError(f"Model response was not valid JSON: {exc}") from second_exc
            else:
                raise ValueError(f"Model response was not valid JSON: {exc}") from exc
        if isinstance(parsed, Mapping):
            data = dict(parsed)
        elif isinstance(parsed, Iterable) and not isinstance(parsed, (str, bytes, bytearray)):
            return _iterable_schema_fallback(parsed)
        else:
            fallback_candidate = str(parsed)
            fallback_text = fallback_candidate if fallback_candidate.strip() else _EMPTY_RESPONSE_FALLBACK
            return {
                "reasoning": "",
                "answer": fallback_text,
                "citations": [],
            }

    reasoning = data.get("reasoning")
    if not isinstance(reasoning, str):
        for key in ("thinking", "thoughts", "chain_of_thought"):
            alt = data.get(key)
            if isinstance(alt, str):
                reasoning = alt
                break
        else:
            reasoning = json.dumps(reasoning) if reasoning is not None else ""
    if isinstance(reasoning, str) and not reasoning.strip():
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
    if isinstance(answer, str) and not answer.strip():
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
        "reasoning": reasoning if isinstance(reasoning, str) else str(reasoning or ""),
        "answer": answer if isinstance(answer, str) else str(answer or ""),
        "citations": citations_list,
        "autopilot": autopilot,
    }


def _extract_model_content(payload: Mapping[str, Any]) -> str:
    message = payload.get("message")
    if isinstance(message, Mapping):
        content_text = _coerce_message_text(message.get("content"))
        if content_text:
            return content_text
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
    context_prelude: str | None = None,
) -> tuple[list[dict[str, Any]], bool, str]:
    messages = [dict(message) for message in base_messages]

    context_bits: list[str] = []
    if url:
        context_bits.append(f"Current page URL: {url}")
    if text_context:
        clipped = text_context[:_MAX_CONTEXT_CHARS]
        context_bits.append("Extracted page text:\n" + clipped)

    system_sections: list[str] = []
    if context_prelude:
        system_sections.append(context_prelude)
    system_sections.append(_SCHEMA_PROMPT)
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


def _preview_bytes(value: str, limit: int = 80) -> str:
    """Return a UTF-8 safe preview clipped to the requested byte length."""

    if not value:
        return ""
    encoded = value.encode("utf-8", errors="ignore")
    if len(encoded) <= limit:
        return value
    return encoded[:limit].decode("utf-8", errors="ignore")


def _log_stream_summary(
    *,
    request_id: str,
    model: str,
    transport: Literal["ndjson", "sse", "json"],
    frames: int,
    previews: list[str],
    end: str,
    trace_id: str | None,
    error: str | None = None,
) -> None:
    """Emit structured logging for chat streaming completions."""

    log_event(
        "INFO",
        "chat.stream_summary",
        trace=trace_id,
        request=request_id,
        model=model,
        transport=transport,
        frames=frames,
        previews=previews,
        end=end,
        error=error,
    )


def _resolve_request_id(candidate: str | None) -> str:
    """Determine the request identifier for downstream logging."""

    trace_id = getattr(g, "trace_id", None)
    header_request = request.headers.get("X-Request-Id") if request else None
    for value in (candidate, header_request, trace_id):
        if isinstance(value, str) and value.strip():
            resolved = value.strip()
            g.chat_request_id = resolved
            return resolved
    generated = uuid.uuid4().hex
    g.chat_request_id = generated
    return generated


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
        content_text = _coerce_message_text(message.get("content"))
        if content_text:
            previous = self.answer
            if content_text != previous:
                delta_text = ""
                next_answer = previous
                if previous and content_text.startswith(previous):
                    delta_text = content_text[len(previous) :]
                    next_answer = content_text
                else:
                    delta_text = content_text
                    next_answer = previous + delta_text
                if delta_text:
                    delta.delta = delta_text
                self.answer = next_answer
                delta.answer = self.answer
        reasoning_value = None
        for key in ("reasoning", "thinking"):
            raw = message.get(key)
            if isinstance(raw, str) and raw.strip():
                reasoning_value = raw.strip()
                break
        if reasoning_value and reasoning_value != self.reasoning:
            self.reasoning = reasoning_value
            delta.reasoning = self.reasoning
        if delta.answer is None and delta.reasoning is None:
            return None
        self.payload = chunk
        return delta


def _iter_streaming_response(
    response: requests.Response,
) -> Iterator[tuple[Mapping[str, Any], ChatStreamDelta, "_StreamAccumulator"]]:
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
            yield payload, delta, accumulator



def _drain_chat_response(response: requests.Response) -> tuple[Mapping[str, Any], _StreamAccumulator]:
    """Consume the streaming response and return the final payload + accumulator."""

    accumulator: _StreamAccumulator | None = None
    final_payload: Mapping[str, Any] | None = None
    for payload, _delta, acc in _iter_streaming_response(response):
        accumulator = acc
        final_payload = payload
    _close_response_safely(response)
    if accumulator is None or accumulator.payload is None or final_payload is None:
        raise ValueError("Upstream response stream was empty")
    return accumulator.payload, accumulator


def _wrap_stream_event(
    event: ChatStreamMetadata | ChatStreamDelta | ChatStreamComplete | ChatStreamError,
) -> tuple[str, Mapping[str, Any]]:
    if isinstance(event, ChatStreamMetadata):
        data = event.model_dump(exclude_none=True, by_alias=True)
        return "chat.metadata", data
    if isinstance(event, ChatStreamDelta):
        chunk = event.delta or event.answer or ""
        data: dict[str, Any] = {
            "type": "text",
            "content": chunk,
        }
        if event.reasoning:
            data["reasoning"] = event.reasoning
        if event.citations:
            data["citations"] = event.citations
        return "chat.delta", data
    if isinstance(event, ChatStreamComplete):
        data = event.payload.model_dump(exclude_none=True)
        return "chat.done", data
    if isinstance(event, ChatStreamError):
        data = event.model_dump(exclude_none=True, by_alias=True)
        return "chat.error", data
    raise TypeError(f"Unsupported stream event {event.__class__.__name__}")


def _serialize_event(event: ChatStreamMetadata | ChatStreamDelta | ChatStreamComplete | ChatStreamError) -> bytes:
    name, payload = _wrap_stream_event(event)
    envelope = {"event": name, "data": payload}
    return (json.dumps(envelope, ensure_ascii=False) + "\n").encode("utf-8")


def _ndjson_stream(events: Iterable[ChatStreamMetadata | ChatStreamDelta | ChatStreamComplete | ChatStreamError]) -> Iterator[bytes]:
    for event in events:
        yield _serialize_event(event)


def _sse_stream(events: Iterable[ChatStreamMetadata | ChatStreamDelta | ChatStreamComplete | ChatStreamError]) -> Iterator[bytes]:
    for event in events:
        name, payload = _wrap_stream_event(event)
        yield (f"event: {name}\n" + "data: " + json.dumps(payload, ensure_ascii=False) + "\n\n").encode("utf-8")


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
    json_mode: bool,
    allowed_tools: set[str] | None,
) -> ChatResponsePayload:
    content = _extract_model_content(payload_json)
    reasoning_text = _extract_model_reasoning(payload_json).strip()
    structured: dict[str, Any] | None = None

    if json_mode and _looks_like_json(content):
        try:
            structured = _coerce_model_schema(content)
        except ValueError as exc:  # pragma: no cover - repair attempts best effort
            LOGGER.debug("Falling back to raw chat content: %s", exc)

    if structured is None:
        structured = {
            "reasoning": reasoning_text or accumulator.reasoning or "",
            "answer": content.strip() or accumulator.answer or "",
            "citations": [],
        }

    if reasoning_text and not structured.get("reasoning"):
        structured["reasoning"] = reasoning_text
    if accumulator.reasoning and not structured.get("reasoning"):
        structured["reasoning"] = accumulator.reasoning
    if accumulator.answer and not structured.get("answer"):
        structured["answer"] = accumulator.answer

    citations = structured.get("citations") or []
    if not isinstance(citations, list):
        citations = []

    base_answer = str(structured.get("answer") or "")
    tool_append = ""
    tool_call = structured.get("tool_call")
    if isinstance(tool_call, Mapping):
        tool_name = str(tool_call.get("name") or "").strip()
        if tool_name and (allowed_tools is None or tool_name in allowed_tools) and tool_name in _TOOL_REGISTRY:
            arguments = tool_call.get("arguments") if isinstance(tool_call, Mapping) else None
            success, tool_result, status_code = _execute_tool_call(tool_name, arguments if isinstance(arguments, Mapping) else None)
            tool_append = _format_tool_append(tool_name, success, tool_result)
            structured["tool_status"] = "success" if success else "error"
            structured["tool_result"] = tool_result
            structured["tool_status_code"] = status_code
            log_event(
                "INFO",
                "chat.tool_executed",
                trace=trace_id,
                model=candidate,
                tool=tool_name,
                status="ok" if success else "error",
                status_code=status_code,
            )
        elif tool_name:
            tool_append = _format_tool_append(tool_name, False, "Tool not available for this request")
            structured["tool_status"] = "skipped"
            structured["tool_status_code"] = 0
            log_event(
                "WARNING",
                "chat.tool_rejected",
                trace=trace_id,
                model=candidate,
                tool=tool_name,
                reason="not_allowed",
            )
    if tool_append:
        prefix = base_answer.strip()
        if prefix:
            base_answer = f"{prefix}\n\n{tool_append}"
        else:
            base_answer = tool_append
        structured["answer"] = base_answer

    answer_text = _guard_contentful_text(
        str(structured.get("answer") or ""),
        fallback=accumulator.answer or content,
    )
    reasoning_value = (structured.get("reasoning") or "").strip() or (accumulator.reasoning or reasoning_text)
    autopilot = _coerce_autopilot(structured.get("autopilot"))
    structured["answer"] = answer_text
    structured["message"] = answer_text

    response_payload = ChatResponsePayload(
        reasoning=(reasoning_value or "").strip(),
        answer=answer_text,
        message=answer_text,
        citations=[str(item) for item in citations if isinstance(item, (str, int, float))],
        model=candidate,
        trace_id=trace_id,
        autopilot=autopilot,
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
    streaming_start: float,
    chat_span: Any,
    image_context: str | None,
    image_used: bool,
    transport: Literal["ndjson", "sse"],
    request_id: str,
    json_mode: bool,
    allowed_tools: set[str] | None,
    single_flight_key: str | None = None,
) -> Response:
    metadata = ChatStreamMetadata(attempt=attempt_index, model=candidate, trace_id=trace_id)
    previews: list[str] = []
    frame_count = 0
    end_reason = "unknown"
    error_message: str | None = None

    def _events() -> Iterable[ChatStreamMetadata | ChatStreamDelta | ChatStreamComplete | ChatStreamError]:
        nonlocal frame_count, end_reason, error_message, single_flight_key
        yield metadata
        accumulator: _StreamAccumulator | None = None
        try:
            for payload, delta, acc in _iter_streaming_response(response):
                accumulator = acc
                frame_count += 1
                preview_source = delta.delta or delta.answer or ""
                if preview_source and len(previews) < 3:
                    previews.append(_preview_bytes(preview_source))
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
                json_mode=json_mode,
                allowed_tools=allowed_tools,
            )
            end_reason = "complete"
            payload_dict = _coerce_schema(payload_model.model_dump(exclude_none=True))
            _publish_payload("io.chat.response", payload_dict)
            yield ChatStreamComplete(payload=payload_model)
        except Exception as exc:  # pragma: no cover - defensive streaming guard
            g.chat_error_class = exc.__class__.__name__
            g.chat_error_message = str(exc)
            error_message = _truncate(str(exc), _MAX_ERROR_PREVIEW)
            log_event(
                "ERROR",
                "chat.error",
                trace=trace_id,
                model=candidate,
                attempt=attempt_index,
                msg=error_message,
            )
            if chat_span is not None:
                chat_span.set_attribute("chat.success", False)
            end_reason = "error"
            _publish_payload(
                "io.chat.response",
                {
                    "error": "stream_error",
                    "hint": "upstream response terminated unexpectedly",
                    "trace_id": trace_id,
                },
            )
            yield ChatStreamError(
                error="stream_error",
                hint="upstream response terminated unexpectedly",
                trace_id=trace_id,
            )
        finally:
            _close_response_safely(response)
            _log_stream_summary(
                request_id=request_id,
                model=candidate,
                transport=transport,
                frames=frame_count,
                previews=previews,
                end=end_reason,
                trace_id=trace_id,
                error=error_message,
            )
            if single_flight_key:
                _SSE_REGISTRY.release(single_flight_key)
                single_flight_key = None

    if transport == "sse":
        body = stream_with_context(_sse_stream(_events()))
        resp = Response(body, mimetype="text/event-stream")
        resp.headers.setdefault("Cache-Control", "no-store, no-transform")
    else:
        body = stream_with_context(_ndjson_stream(_events()))
        resp = Response(body, mimetype="application/x-ndjson")
        resp.headers.setdefault("Cache-Control", "no-store")
    resp.headers["X-LLM-Model"] = candidate
    resp.headers.setdefault("X-Accel-Buffering", "no")
    resp.headers["X-Request-Id"] = request_id
    return resp



def _execute_chat_request(
    chat_request: ChatRequest,
    *,
    start_time: float,
    streaming_override: bool | None,
    stream_transport: Literal["ndjson", "sse"],
) -> Response:
    sanitized_messages = [msg.model_dump(exclude_none=True) for msg in chat_request.messages]
    context_payload = dict(chat_request.context or {})
    tool_specs = chat_request.tools or []
    serialized_tools: list[Mapping[str, Any]] = [tool.model_dump(exclude_none=True) for tool in tool_specs]
    allowed_tool_names: set[str] | None = None
    if serialized_tools:
        allowed_tool_names = {
            stripped
            for stripped in (
                str(entry.get("name") or "").strip()
                for entry in serialized_tools
                if entry.get("name")
            )
            if stripped
        }
    _maybe_index_page_context(context_payload)
    context_prelude, context_meta = _render_context_prelude(context_payload, serialized_tools)

    thread_id = _ensure_thread_context(chat_request)

    chat_logger = current_app.config.get("CHAT_LOGGER")
    if hasattr(chat_logger, "info"):
        preview = " | ".join(entry.get("content", "") for entry in sanitized_messages)
        chat_logger.info("chat request received: %s", preview.strip())

    request_id = _resolve_request_id(chat_request.request_id)

    if thread_id and isinstance(context_payload, dict):
        context_payload.setdefault("thread_id", thread_id)

    requested_model = chat_request.model
    url_value = chat_request.url
    text_context = chat_request.text_context
    image_context = chat_request.image_context
    client_timezone = chat_request.client_timezone
    server_time = chat_request.server_time
    server_timezone = chat_request.server_timezone
    server_time_utc = chat_request.server_time_utc
    trace_id = getattr(g, "trace_id", None)

    allowed_alias_list = list(allowed_model_aliases())
    resolved_requested_model: str | None = None
    if requested_model:
        try:
            resolved_requested_model = normalize_model_alias(requested_model)
        except ValueError as exc:
            g.chat_error_class = "ModelNotAllowed"
            g.chat_error_message = "unsupported_model"
            error_response = jsonify(
                {
                    "error": "unsupported_model",
                    "detail": str(exc),
                    "allowed": allowed_alias_list,
                    "trace_id": trace_id,
                }
            )
            error_response.status_code = 400
            error_response.headers["X-Request-Id"] = request_id
            return error_response

    primary_model, fallback_model, _ = _configured_models()

    accept_header = (request.headers.get("Accept") or "").lower()
    stream_flag = request.args.get("stream")
    if streaming_override is not None:
        streaming_requested = bool(streaming_override)
    elif chat_request.stream is not None:
        streaming_requested = bool(chat_request.stream)
    elif stream_flag is not None:
        streaming_requested = stream_flag.strip().lower() not in {"0", "false", "no", "off"}
    else:
        streaming_requested = "application/json" not in accept_header

    single_flight_key: str | None = None
    try:
        if streaming_requested and stream_transport == "sse":
            if not _SSE_REGISTRY.claim(request_id):
                g.chat_error_class = "DuplicateStream"
                g.chat_error_message = "duplicate_stream"
                detail = {
                    "request_id": request_id,
                    "model": requested_model,
                    "transport": stream_transport,
                }
                _record_incident(
                    _INCIDENT_DUPLICATE_SSE,
                    message="Blocked duplicate chat stream for active request.",
                    detail=detail,
                )
                log_event(
                    "WARNING",
                    "chat.duplicate_stream",
                    trace=trace_id,
                    request=request_id,
                    model=requested_model,
                )
                response = jsonify(
                    {
                        "error": "duplicate_stream",
                        "message": "A chat stream is already in progress for this request.",
                        "trace_id": trace_id,
                        "request_id": request_id,
                        "incident": {
                            "type": _INCIDENT_DUPLICATE_SSE,
                            "detail": detail,
                        },
                    }
                )
                response.status_code = 409
                response.headers["X-Request-Id"] = request_id
                return response
            single_flight_key = request_id

        trace_inputs = {
            "message_count": len(sanitized_messages),
            "requested_model": requested_model,
            "has_context": bool(text_context or image_context or context_payload),
            "request_id": request_id,
            "transport": stream_transport if streaming_requested else "json",
        }
        for key, value in context_meta.items():
            if isinstance(value, (str, int, float, bool)):
                trace_inputs[f"context.{key}"] = value

        with start_span(
            "http.chat",
            attributes={"http.route": "/api/chat", "http.method": request.method},
            inputs=trace_inputs,
        ) as chat_span:
            candidate_pairs: list[tuple[str | None, str]] = []
            seen_models: set[str] = set()

        def _add_candidate(label: str | None, canonical: str | None) -> None:
            if not canonical:
                return
            key = canonical.strip().lower()
            if not key or key in seen_models:
                return
            seen_models.add(key)
            candidate_pairs.append((label, canonical))

        if resolved_requested_model:
            _add_candidate(requested_model, resolved_requested_model)
        else:
            _add_candidate(None, primary_model)
            if fallback_model and fallback_model != primary_model:
                _add_candidate(None, fallback_model)

        if not candidate_pairs:
            _add_candidate(None, normalize_model_alias(None))

        if chat_span is not None:
            chat_span.set_attribute("chat.candidate_count", len(candidate_pairs))

        config: AppConfig = current_app.config["APP_CONFIG"]
        endpoint = _chat_endpoint(config)

        attempted: list[str] = []
        missing_reasons: list[str] = []

        for attempt_index, (alias_label, candidate) in enumerate(candidate_pairs, start=1):
            display_model = alias_label or candidate
            attempted.append(display_model)
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
                context_prelude=context_prelude,
            )

            log_event(
                "INFO",
                "chat.request",
                trace=trace_id,
                model=candidate,
                alias=alias_label if alias_label and alias_label != candidate else None,
                attempt=attempt_index,
                url=url_value,
                has_text=bool(text_context),
                has_img=bool(image_context),
            )

            if hasattr(chat_logger, "info"):
                chat_logger.info("forwarding chat request to ollama (model=%s)", display_model)

            upstream_model = alias_label or candidate
            request_payload: dict[str, Any] = {
                "model": upstream_model,
                "messages": prepared_messages,
                "stream": bool(streaming_requested),
                "system": system_prompt,
                "request_id": request_id,
            }
            json_mode = False
            if _supports_json_format(candidate):
                request_payload["format"] = "json"
                json_mode = True
            else:
                log_event(
                    "INFO",
                    "chat.json_disabled",
                    trace=trace_id,
                    model=display_model,
                )

            response = None
            attempt_start = time.perf_counter()
            try:
                with start_span(
                    "llm.chat",
                    attributes={"llm.model": display_model, "llm.attempt": attempt_index},
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
                    model=display_model,
                    attempt=attempt_index,
                    error=g.chat_error_class,
                    msg=_truncate(str(exc), _MAX_ERROR_PREVIEW),
                )
                error_response = jsonify(
                    {
                        "error": "upstream_unavailable",
                        "message": str(exc),
                        "trace_id": trace_id,
                    }
                )
                error_response.status_code = 502
                error_response.headers["X-Request-Id"] = request_id
                _log_stream_summary(
                    request_id=request_id,
                    model=candidate,
                    transport=stream_transport if streaming_requested else "json",
                    frames=0,
                    previews=[],
                    end="error",
                    trace_id=trace_id,
                    error=g.chat_error_message,
                )
                return error_response

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
                    model=display_model,
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
                    model=display_model,
                    code=response.status_code,
                    msg=g.chat_error_message,
                )
                response.close()
                error_response = jsonify(
                    {
                        "error": "upstream_error",
                        "status": response.status_code,
                        "message": g.chat_error_message,
                        "trace_id": trace_id,
                    }
                )
                error_response.status_code = response.status_code
                error_response.headers["X-Request-Id"] = request_id
                _log_stream_summary(
                    request_id=request_id,
                    model=display_model,
                    transport=stream_transport if streaming_requested else "json",
                    frames=0,
                    previews=[],
                    end="error",
                    trace_id=trace_id,
                    error=g.chat_error_message,
                )
                return error_response

            if streaming_requested:
                release_key = single_flight_key if stream_transport == "sse" else None
                if stream_transport == "sse":
                    single_flight_key = None
                return _stream_chat_response(
                    candidate=display_model,
                    attempt_index=attempt_index,
                    response=response,
                    trace_id=trace_id,
                    streaming_start=attempt_start,
                    chat_span=chat_span,
                    image_context=image_context,
                    image_used=image_used,
                    transport=stream_transport,
                    request_id=request_id,
                    json_mode=json_mode,
                    allowed_tools=allowed_tool_names,
                    single_flight_key=release_key,
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
                    msg=g.chat_error_message,
                )
                error_response = jsonify(
                    {
                        "error": "invalid_response",
                        "message": str(exc),
                        "trace_id": trace_id,
                    }
                )
                error_response.status_code = 502
                error_response.headers["X-Request-Id"] = request_id
                _log_stream_summary(
                    request_id=request_id,
                    model=candidate,
                    transport="json",
                    frames=0,
                    previews=[],
                    end="error",
                    trace_id=trace_id,
                    error=g.chat_error_message,
                )
                return error_response

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
                error_response = jsonify(
                    {
                        "error": "invalid_response",
                        "message": g.chat_error_message,
                        "trace_id": trace_id,
                    }
                )
                error_response.status_code = 502
                error_response.headers["X-Request-Id"] = request_id
                _log_stream_summary(
                    request_id=request_id,
                    model=candidate,
                    transport="json",
                    frames=0,
                    previews=[],
                    end="error",
                    trace_id=trace_id,
                    error=g.chat_error_message,
                )
                return error_response

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
                json_mode=json_mode,
                allowed_tools=allowed_tool_names,
            )

            preview_source = response_payload.answer or response_payload.reasoning or ""
            previews = [_preview_bytes(preview_source)] if preview_source else []
            _log_stream_summary(
                request_id=request_id,
                model=display_model,
                transport="json",
                frames=1,
                previews=previews,
                end="complete",
                trace_id=response_payload.trace_id or trace_id,
            )

            payload_dict = _coerce_schema(response_payload.model_dump(exclude_none=True))
            _publish_payload("io.chat.response", payload_dict)
            flask_response = jsonify(payload_dict)
            flask_response.headers["X-LLM-Model"] = candidate
            flask_response.headers["X-Request-Id"] = request_id
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
        error_response = jsonify(
            {
                "error": "model_not_found",
                "tried": tried,
                "hint": hint,
                "trace_id": trace_id,
            }
        )
        error_response.status_code = 503
        error_response.headers["X-Request-Id"] = request_id
        _publish_payload(
            "io.chat.response",
            {
                "error": "model_not_found",
                "tried": tried,
                "hint": hint,
                "trace_id": trace_id,
            },
        )
        _log_stream_summary(
            request_id=request_id,
            model=primary_model,
            transport=stream_transport if streaming_requested else "json",
            frames=0,
            previews=[],
            end="error",
            trace_id=trace_id,
            error=combined,
        )
        return error_response
    finally:
        if single_flight_key is not None:
            _SSE_REGISTRY.release(single_flight_key)


@bp.post("/chat")
def chat_invoke() -> Response:
    start = time.perf_counter()
    raw_payload = request.get_json(silent=True) or {}
    # Back-compat shim: allow minimal {"message": "...", "model": "..."}
    # by converting to full ChatRequest shape expected by the validator.
    try:
        if isinstance(raw_payload, Mapping):
            if "message" in raw_payload and "messages" not in raw_payload:
                message_val = raw_payload.get("message")
                model_val = raw_payload.get("model")
                if isinstance(message_val, str) and message_val.strip():
                    patched: dict[str, Any] = {"messages": [{"role": "user", "content": message_val.strip()}]}
                    if isinstance(model_val, str) and model_val.strip():
                        patched["model"] = model_val.strip()
                    # Preserve explicit stream flag if provided
                    stream_val = raw_payload.get("stream")
                    if isinstance(stream_val, (bool, str, int)):
                        patched["stream"] = stream_val  # validator will coerce
                    raw_payload = patched
    except Exception:  # pragma: no cover - defensive
        pass
    try:
        chat_request = ChatRequest.model_validate(raw_payload)
    except ValidationError as exc:
        g.chat_error_class = "ValidationError"
        g.chat_error_message = "invalid_request"
        request_id = _resolve_request_id(None)
        _publish_payload("io.chat.request", _shrink_payload(raw_payload))
        error_response = jsonify(
            {
                "error": "validation_error",
                "detail": exc.errors(),
                "trace_id": getattr(g, "trace_id", None),
            }
        )
        error_response.status_code = 400
        error_response.headers["X-Request-Id"] = request_id
        _publish_payload(
            "io.chat.response",
            {
                "error": "validation_error",
                "detail": exc.errors(),
                "trace_id": getattr(g, "trace_id", None),
            },
        )
        _log_stream_summary(
            request_id=request_id,
            model="unknown",
            transport="json",
            frames=0,
            previews=[],
            end="error",
            trace_id=getattr(g, "trace_id", None),
            error="validation_error",
        )
        return error_response

    # Reject requests that contain no non-empty user message content
    try:
        if not any(
            (getattr(msg, "role", "").lower() == "user" and getattr(msg, "content", "").strip())
            for msg in chat_request.messages
        ):
            request_id = _resolve_request_id(None)
            g.chat_error_class = "EmptyMessage"
            g.chat_error_message = "EMPTY_MESSAGE"
            error_response = jsonify({"error": "EMPTY_MESSAGE"})
            error_response.status_code = 400
            error_response.headers["X-Request-Id"] = request_id
            _publish_payload("io.chat.response", {"error": "EMPTY_MESSAGE", "trace_id": getattr(g, "trace_id", None)})
            _log_stream_summary(
                request_id=request_id,
                model="unknown",
                transport="json",
                frames=0,
                previews=[],
                end="error",
                trace_id=getattr(g, "trace_id", None),
                error="EMPTY_MESSAGE",
            )
            return error_response
    except Exception:
        # best-effort guard; proceed to execution if validation above fails unexpectedly
        pass

    _publish_payload("io.chat.request", chat_request.model_dump(exclude_none=True))
    return _execute_chat_request(
        chat_request,
        start_time=start,
        streaming_override=None,
        stream_transport="ndjson",
    )


@bp.post("/chat/stream")
def chat_stream() -> Response:
    start = time.perf_counter()
    raw_payload = request.get_json(silent=True) or {}
    # Back-compat shim mirroring chat_invoke: accept {message, model}
    try:
        if isinstance(raw_payload, Mapping):
            if "message" in raw_payload and "messages" not in raw_payload:
                message_val = raw_payload.get("message")
                model_val = raw_payload.get("model")
                if isinstance(message_val, str) and message_val.strip():
                    patched: dict[str, Any] = {"messages": [{"role": "user", "content": message_val.strip()}], "stream": True}
                    if isinstance(model_val, str) and model_val.strip():
                        patched["model"] = model_val.strip()
                    raw_payload = patched
    except Exception:  # pragma: no cover - defensive
        pass
    try:
        chat_request = ChatRequest.model_validate(raw_payload)
    except ValidationError as exc:
        g.chat_error_class = "ValidationError"
        g.chat_error_message = "invalid_request"
        request_id = _resolve_request_id(None)
        _publish_payload("io.chat.request", _shrink_payload(raw_payload))
        error_response = jsonify(
            {
                "error": "validation_error",
                "detail": exc.errors(),
                "trace_id": getattr(g, "trace_id", None),
            }
        )
        error_response.status_code = 400
        error_response.headers["X-Request-Id"] = request_id
        _publish_payload(
            "io.chat.response",
            {
                "error": "validation_error",
                "detail": exc.errors(),
                "trace_id": getattr(g, "trace_id", None),
            },
        )
        _log_stream_summary(
            request_id=request_id,
            model="unknown",
            transport="sse",
            frames=0,
            previews=[],
            end="error",
            trace_id=getattr(g, "trace_id", None),
            error="validation_error",
        )
        return error_response

    # Reject requests that contain no non-empty user message content (streaming path)
    try:
        if not any(
            (getattr(msg, "role", "").lower() == "user" and getattr(msg, "content", "").strip())
            for msg in chat_request.messages
        ):
            request_id = _resolve_request_id(None)
            g.chat_error_class = "EmptyMessage"
            g.chat_error_message = "EMPTY_MESSAGE"
            error_response = jsonify({"error": "EMPTY_MESSAGE"})
            error_response.status_code = 400
            error_response.headers["X-Request-Id"] = request_id
            _publish_payload("io.chat.response", {"error": "EMPTY_MESSAGE", "trace_id": getattr(g, "trace_id", None)})
            _log_stream_summary(
                request_id=request_id,
                model="unknown",
                transport="sse",
                frames=0,
                previews=[],
                end="error",
                trace_id=getattr(g, "trace_id", None),
                error="EMPTY_MESSAGE",
            )
            return error_response
    except Exception:
        # best-effort guard
        pass

    _publish_payload("io.chat.request", chat_request.model_dump(exclude_none=True))
    return _execute_chat_request(
        chat_request,
        start_time=start,
        streaming_override=True,
        stream_transport="sse",
    )


__all__ = ["bp"]
