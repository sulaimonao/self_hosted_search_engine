"""Decorators and helpers for tool telemetry logging."""

from __future__ import annotations

import time
from functools import wraps
from typing import Any, Callable, Mapping, MutableMapping

try:  # pragma: no cover - optional flask dependency for tooling
    from flask import g, has_app_context, has_request_context
except Exception:  # pragma: no cover - allows usage without flask context
    g = None  # type: ignore

    def has_app_context() -> bool:  # type: ignore
        return False

    def has_request_context() -> bool:  # type: ignore
        return False

from backend.logging_utils import event_base, redact, write_event
from server.runlog import add_run_log_line

ToolFunc = Callable[..., Any]


def _summarize_success(tool_name: str, params: Mapping[str, Any], result: Any) -> str:
    if isinstance(result, Mapping):
        if tool_name == "index.search":
            hits = result.get("results")
            hit_count = len(hits) if isinstance(hits, list) else 0
            k = params.get("k") if isinstance(params, Mapping) else None
            return f"searched local index (hits={hit_count}, k={k or 'default'})"
        if tool_name == "index.upsert":
            changed = result.get("chunks")
            skipped = result.get("skipped")
            if skipped:
                return "index upsert skipped"
            return f"indexed {changed or 0} chunks"
        if tool_name == "crawl.fetch":
            status = result.get("status_code")
            return f"fetched page status={status}"
        if tool_name == "crawl.seeds":
            count = result.get("count")
            return f"gathered {count or 0} seeds"
        if tool_name == "embed.documents":
            count = result.get("count")
            return f"embedded {count or 0} documents"
        if tool_name == "embed.query":
            dims = result.get("dimensions")
            return f"embedded query dims={dims or 0}"
    return f"{tool_name} ok"


def _summarize_error(tool_name: str, error: Mapping[str, Any]) -> str:
    detail = error.get("error") if isinstance(error, Mapping) else None
    if isinstance(detail, str) and detail:
        return f"{tool_name} error: {detail[:120]}"
    return f"{tool_name} error"


def _get_context_attr(name: str) -> Any:
    """Safely retrieve attributes from ``flask.g`` when available."""

    if g is None:
        return None
    try:
        if not (has_request_context() or has_app_context()):
            return None
    except RuntimeError:  # pragma: no cover - defensive for partial flask setup
        return None
    try:
        return getattr(g, name, None)
    except RuntimeError:
        return None


def log_tool(tool_name: str) -> Callable[[ToolFunc], ToolFunc]:
    """Decorator emitting start/end/error events around tool execution."""

    def decorator(fn: ToolFunc) -> ToolFunc:
        @wraps(fn)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            start = time.time()
            request_id = _get_context_attr("request_id")
            session_id = _get_context_attr("session_id")
            write_event(
                event_base(
                    event="tool.start",
                    level="INFO",
                    tool=tool_name,
                    request_id=request_id,
                    session_id=session_id,
                    msg=f"{tool_name} start",
                    meta={"kwargs": redact(kwargs)},
                )
            )
            try:
                result = fn(*args, **kwargs)
            except Exception as exc:
                duration_ms = int((time.time() - start) * 1000)
                write_event(
                    event_base(
                        event="tool.error",
                        level="ERROR",
                        tool=tool_name,
                        request_id=request_id,
                        session_id=session_id,
                        duration_ms=duration_ms,
                        status="error",
                        msg=f"{tool_name} failed: {type(exc).__name__}",
                        meta={"error": redact(str(exc))},
                    )
                )
                add_run_log_line(_summarize_error(tool_name, {"error": str(exc)}))
                raise
            duration_ms = int((time.time() - start) * 1000)
            write_event(
                event_base(
                    event="tool.end",
                    level="INFO",
                    tool=tool_name,
                    request_id=request_id,
                    session_id=session_id,
                    duration_ms=duration_ms,
                    status="ok",
                    msg=f"{tool_name} ok",
                    meta={"result_preview": redact(result)},
                )
            )
            if isinstance(result, MutableMapping) and result.get("ok") is not None:
                payload: Mapping[str, Any] = result
            else:
                payload = {"ok": True, "result": result}
            add_run_log_line(_summarize_success(tool_name, kwargs, payload.get("result")))
            return result

        return wrapped

    return decorator


__all__ = ["log_tool"]
