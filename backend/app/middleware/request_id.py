"""Request middleware that assigns per-request trace identifiers."""

from __future__ import annotations

import time

from flask import g, request

from backend.logging_utils import new_request_id
from backend.app.observability import log_inbound_http_traffic
from backend.app.logging_setup import get_request_logger


_REQUEST_LOGGER = get_request_logger()


def before_request() -> None:
    """Attach a trace identifier to ``flask.g`` for downstream logging."""

    trace_id = getattr(g, "trace_id", None)
    if not trace_id:
        header_id = (
            request.headers.get("X-Correlation-Id")
            or request.headers.get("X-Trace-Id")
            or request.headers.get("X-Request-Id")
        )
        trace_id = header_id or new_request_id()
    g.trace_id = trace_id
    g.request_id = trace_id
    g.correlation_id = trace_id
    g.request_start = getattr(g, "request_start", time.time())
    g._request_perf_start = getattr(g, "_request_perf_start", time.perf_counter())


def after_request(response):  # type: ignore[no-untyped-def]
    """Emit a concise summary log and propagate the trace header."""

    start_perf: float | None = getattr(g, "_request_perf_start", None)
    duration_ms: int | None = None
    if isinstance(start_perf, (int, float)):
        duration_ms = int((time.perf_counter() - start_perf) * 1000)
    trace_id: str | None = getattr(g, "trace_id", None)

    log_inbound_http_traffic(response, duration_ms)

    extra_meta = {
        "method": request.method,
        "path": request.path,
        "status": response.status_code,
        "duration_ms": duration_ms,
        "remote_addr": request.headers.get("X-Forwarded-For")
        or request.headers.get("X-Real-IP")
        or request.remote_addr,
    }
    _REQUEST_LOGGER.info(
        "HTTP %s %s -> %s (%sms)",
        request.method,
        request.path,
        response.status_code,
        duration_ms if duration_ms is not None else -1,
        extra={
            "correlation_id": trace_id,
            "component": "flask-api",
            "meta": extra_meta,
        },
    )

    if trace_id:
        response.headers.setdefault("X-Request-Id", trace_id)
        response.headers.setdefault("X-Correlation-Id", trace_id)
    return response


__all__ = ["before_request", "after_request"]
