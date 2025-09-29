"""Flask middleware emitting structured request telemetry."""

from __future__ import annotations

import time
from typing import Any, Dict

from flask import Response, current_app, g, request

from backend.logging_utils import event_base, new_request_id, redact, write_event
from server.runlog import current_run_log


def before_request() -> None:
    g.request_start = time.time()
    g.request_id = request.headers.get("X-Request-Id") or new_request_id()
    g.session_id = request.headers.get("X-Session-Id", "sess_anon")
    g.user_id = request.headers.get("X-User-Id", "anon")
    current_run_log(create=True)

    payload = request.get_json(silent=True) or {}
    meta: Dict[str, Any] = {
        "route": f"{request.method} {request.path}",
        "payload": redact(payload),
    }
    headers = {k: v for k, v in request.headers.items() if k.lower() in {"content-type", "user-agent"}}
    if headers:
        meta["headers"] = redact(headers)

    write_event(
        event_base(
            event="req.start",
            level="INFO",
            route=f"{request.method} {request.path}",
            request_id=g.request_id,
            session_id=g.session_id,
            user_id=g.user_id,
            bytes_in=len(request.data or b""),
            msg="incoming request",
            meta=meta,
        )
    )


def after_request(response: Response) -> Response:
    start = getattr(g, "request_start", time.time())
    duration_ms = int((time.time() - start) * 1000)
    content_length = response.calculate_content_length()
    write_event(
        event_base(
            event="req.end",
            level="INFO",
            route=f"{request.method} {request.path}",
            request_id=getattr(g, "request_id", None),
            session_id=getattr(g, "session_id", None),
            user_id=getattr(g, "user_id", None),
            duration_ms=duration_ms,
            http_status=response.status_code,
            bytes_out=content_length if content_length is not None else 0,
            msg="request complete",
            meta={"headers": redact(dict(response.headers))},
        )
    )
    response.headers.setdefault("X-Request-Id", str(getattr(g, "request_id", "")))

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
