"""Request middleware that assigns per-request trace identifiers."""

from __future__ import annotations

import time

from flask import g, request

from backend.logging_utils import new_request_id
from backend.app.observability import log_inbound_http_traffic


def before_request() -> None:
    """Attach a trace identifier to ``flask.g`` for downstream logging."""

    trace_id = getattr(g, "trace_id", None)
    if not trace_id:
        header_id = request.headers.get("X-Trace-Id") or request.headers.get(
            "X-Request-Id"
        )
        trace_id = header_id or new_request_id()
    g.trace_id = trace_id
    g.request_id = trace_id
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

    if trace_id:
        response.headers.setdefault("X-Request-Id", trace_id)
    return response


__all__ = ["before_request", "after_request"]
