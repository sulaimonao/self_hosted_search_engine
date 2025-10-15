"""Application telemetry helpers for local development and LangSmith tracing."""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator, Mapping

try:  # Optional import: during CLI usage there may be no Flask app context
    from flask import g
except Exception:  # pragma: no cover - allows module use without Flask available
    g = None  # type: ignore

from backend.logging_utils import redact
from server.json_logger import log_event
from server.runlog import current_run_log

LOGGER = logging.getLogger(__name__)

_TRACE_ENABLED = False
_PROJECT_NAME = "self-hosted-search"
_SERVICE_NAME = "self_hosted_search_engine.api"


def configure_tracing(
    app: Any,
    *,
    enabled: bool,
    project_name: str,
    service_name: str,
) -> None:
    """Configure LangSmith/OTel tracing hooks on the running Flask app."""

    global _TRACE_ENABLED, _PROJECT_NAME, _SERVICE_NAME

    _TRACE_ENABLED = bool(enabled)
    _PROJECT_NAME = project_name or _PROJECT_NAME
    _SERVICE_NAME = service_name or _SERVICE_NAME

    app.config["OBS_TRACE_ENABLED"] = _TRACE_ENABLED
    app.config["OBS_TRACE_PROJECT"] = _PROJECT_NAME
    app.config["OBS_TRACE_SERVICE"] = _SERVICE_NAME

    if not _TRACE_ENABLED:
        LOGGER.info("Observability tracing disabled (LANGSMITH_ENABLED=0)")
        return

    try:
        from langsmith import Client  # type: ignore

        client = Client()
        app.config["OBS_TRACE_CLIENT"] = client
        LOGGER.info(
            "LangSmith tracing enabled for project=%s service=%s",
            _PROJECT_NAME,
            _SERVICE_NAME,
        )
    except Exception as exc:  # pragma: no cover - graceful degradation
        LOGGER.warning("LangSmith tracing unavailable: %s", exc)


@dataclass
class _SpanHandle:
    name: str
    attributes: dict[str, Any] = field(default_factory=dict)
    error: dict[str, Any] | None = None

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[str(key)] = value

    def record_exception(self, exc: BaseException) -> None:
        self.error = {
            "type": exc.__class__.__name__,
            "message": str(exc),
        }


def _current_trace_id() -> str | None:
    if g is None:  # pragma: no cover - accessed outside Flask context
        return None
    try:
        return getattr(g, "trace_id", None)
    except RuntimeError:  # pragma: no cover - Flask context missing
        return None


def _emit_span_event(
    *,
    span: _SpanHandle,
    suffix: str,
    level: str,
    duration_ms: int | None,
    inputs: Any,
) -> None:
    trace_id = _current_trace_id()
    meta: dict[str, Any] = {}
    if span.attributes:
        meta["attributes"] = redact(span.attributes)
    if inputs is not None:
        meta["inputs"] = redact(inputs)
    if span.error:
        meta["error"] = redact(span.error)
    meta.setdefault("project", _PROJECT_NAME)
    meta.setdefault("service", _SERVICE_NAME)

    kwargs: dict[str, Any] = {"trace": trace_id, "msg": span.name}
    if duration_ms is not None:
        kwargs["duration_ms"] = duration_ms
    if meta:
        kwargs["meta"] = meta

    log_event(level, f"{span.name}.{suffix}", **kwargs)


@contextmanager
def start_span(
    name: str,
    *,
    attributes: Mapping[str, Any] | None = None,
    inputs: Any | None = None,
) -> Iterator[_SpanHandle]:
    """Return a context manager that records start/end events for ``name``."""

    span = _SpanHandle(name=name, attributes=dict(attributes or {}))
    run_log = current_run_log(create=False)
    if run_log and _TRACE_ENABLED:
        run_log.add(f"{name}: started")

    start_time = time.perf_counter()
    _emit_span_event(
        span=span, suffix="start", level="DEBUG", duration_ms=None, inputs=inputs
    )

    try:
        yield span
    except Exception as exc:
        span.record_exception(exc)
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        _emit_span_event(
            span=span,
            suffix="error",
            level="ERROR",
            duration_ms=duration_ms,
            inputs=inputs,
        )
        if run_log and _TRACE_ENABLED:
            message = span.error.get("message") if span.error else "error"
            run_log.add(f"{name}: failed ({message})")
        raise
    else:
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        _emit_span_event(
            span=span,
            suffix="end",
            level="INFO",
            duration_ms=duration_ms,
            inputs=inputs,
        )
        if run_log and _TRACE_ENABLED:
            run_log.add(f"{name}: completed in {duration_ms}ms")


__all__ = ["configure_tracing", "start_span"]
