"""Flask middleware emitting JSON request/response traces."""

from __future__ import annotations

import time
from typing import Any, Dict

from flask import Response, current_app, g, request

from backend.logging_utils import new_request_id, redact
from server.json_logger import log_event
from server.runlog import current_run_log


def before_request() -> None:
    g.request_start = time.time()
    trace_id = request.headers.get("X-Request-Id") or new_request_id()
    g.request_id = trace_id
    g.trace_id = trace_id
    g.session_id = request.headers.get("X-Session-Id", "sess_anon")
    g.user_id = request.headers.get("X-User-Id", "anon")
    current_run_log(create=True)

    payload = request.get_json(silent=True) or {}
    headers = {
        k: v
        for k, v in request.headers.items()
        if k.lower() in {"content-type", "user-agent"}
    }
    meta: Dict[str, Any] = {"payload": redact(payload)}
    if headers:
        meta["headers"] = redact(headers)

    log_event(
        "INFO",
        "http.request",
        trace=trace_id,
        method=request.method,
        path=request.path,
        bytes_in=len(request.data or b""),
        session=g.session_id,
        user=g.user_id,
        **meta,
    )


def after_request(response: Response) -> Response:
    start = getattr(g, "request_start", time.time())
    duration_ms = int((time.time() - start) * 1000)
    content_length = response.calculate_content_length() or 0
    trace_id = getattr(g, "trace_id", None)

    extras: Dict[str, Any] = {}
    if request.path.startswith("/api/chat"):
        extras.update(
            {
                "model": getattr(g, "chat_model", None),
                "fallback_used": getattr(g, "chat_fallback_used", None),
                "error": getattr(g, "chat_error_class", None),
                "error_msg": getattr(g, "chat_error_message", None),
            }
        )

    log_event(
        "INFO",
        "http.response",
        trace=trace_id,
        method=request.method,
        path=request.path,
        status=response.status_code,
        duration_ms=duration_ms,
        bytes_out=content_length,
        **{k: v for k, v in extras.items() if v is not None},
    )

    response.headers.setdefault("X-Request-Id", str(trace_id or ""))

    if request.path.startswith("/api"):
        allowed_origin = current_app.config.get("FRONTEND_ORIGIN")
        if allowed_origin:
            response.headers.setdefault("Access-Control-Allow-Origin", allowed_origin)
            response.headers.setdefault("Access-Control-Allow-Credentials", "true")
            response.headers.setdefault(
                "Access-Control-Allow-Headers",
                "Content-Type,Authorization,X-Requested-With",
            )
            response.headers.setdefault(
                "Access-Control-Allow-Methods",
                "GET,POST,PUT,PATCH,DELETE,OPTIONS",
            )
            vary_header = response.headers.get("Vary")
            if vary_header:
                if "origin" not in vary_header.lower():
                    response.headers["Vary"] = f"{vary_header}, Origin"
            else:
                response.headers["Vary"] = "Origin"
    return response


__all__ = ["before_request", "after_request"]
