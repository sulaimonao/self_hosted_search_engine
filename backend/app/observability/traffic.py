"""Traffic logging helpers to capture inbound and outbound HTTP activity."""

from __future__ import annotations

import functools
import json
import random
import time
from typing import Any, Mapping, MutableMapping, Sequence
from urllib.parse import urlparse

from backend.logging_utils import MAX_FIELD_BYTES, LOG_SAMPLE_PCT, redact
from server.json_logger import log_event

_SENSITIVE_HEADER_KEYS = {
    "authorization",
    "proxy-authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "x-auth-token",
    "x-ollama-session",
    "x-sentry-token",
}

_requests_patched = False


def _should_sample() -> bool:
    pct = max(0.0, min(1.0, LOG_SAMPLE_PCT))
    if pct >= 1.0:
        return True
    return random.random() <= pct


def _truncate(value: str, limit: int = 512) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


def _sanitize_headers(headers: Mapping[str, Any] | None) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    if not headers:
        return sanitized
    for key, value in headers.items():
        key_str = str(key)
        lower = key_str.lower()
        if lower in _SENSITIVE_HEADER_KEYS:
            sanitized[key_str] = "[REDACTED]"
            continue
        if isinstance(value, (list, tuple, set)):
            flattened = ", ".join(str(v) for v in value)
        else:
            flattened = str(value)
        sanitized[key_str] = _truncate(flattened)
    return sanitized


def _response_length(response: Any) -> int | None:
    if response is None:
        return None
    try:
        if hasattr(response, "calculate_content_length"):
            length = response.calculate_content_length()
            if isinstance(length, int):
                return length
    except Exception:  # pragma: no cover - defensive
        pass
    try:
        header_len = response.headers.get("Content-Length")  # type: ignore[union-attr]
        if header_len:
            return int(header_len)
    except Exception:
        pass
    if getattr(response, "direct_passthrough", False):
        return None
    try:
        data = response.get_data()  # type: ignore[union-attr]
        if data is not None:
            return len(data)
    except Exception:
        return None
    return None


def _safe_request_body_snapshot(req: Any) -> Any:
    try:
        if req.is_json:
            payload = req.get_json(silent=True)
            if payload is not None:
                return redact(payload)
        if req.mimetype and "form" in req.mimetype and req.form:
            return {"form_keys": sorted(req.form.keys())}
    except Exception:
        return None
    return None


def log_inbound_http_traffic(response: Any, duration_ms: int | None) -> None:
    """Emit a structured log describing the handled Flask request."""

    if not _should_sample():
        return
    try:
        from flask import g, request

        trace_id = getattr(g, "trace_id", None)
        query_string = ""
        try:
            query_string = request.query_string.decode("utf-8", "ignore")
        except Exception:
            query_string = ""

        headers = _sanitize_headers(request.headers)
        response_headers = _sanitize_headers(getattr(response, "headers", None))
        body_snapshot = _safe_request_body_snapshot(request)
        remote_addr = (
            request.headers.get("X-Forwarded-For")
            or request.headers.get("X-Real-IP")
            or request.remote_addr
        )

        meta: dict[str, Any] = {
            "direction": "inbound",
            "remote_addr": remote_addr,
            "endpoint": request.endpoint,
            "query_string": _truncate(query_string, 1024),
            "user_agent": request.user_agent.string if request.user_agent else None,
            "request_headers": headers,
            "response_headers": response_headers,
        }
        if body_snapshot is not None:
            meta["request_body"] = body_snapshot

        log_event(
            "INFO",
            "traffic.http.server",
            trace=trace_id,
            method=request.method,
            path=request.path,
            status=response.status_code,
            duration_ms=duration_ms,
            bytes_in=request.content_length,
            bytes_out=_response_length(response),
            component="backend.api",
            meta=meta,
        )
    except Exception:
        # Never let logging break the request lifecycle
        return


def _current_trace_id() -> str | None:
    try:
        from flask import g

        return getattr(g, "trace_id", None)
    except Exception:
        return None


def _body_length_from_kwargs(kwargs: MutableMapping[str, Any]) -> int | None:
    if "json" in kwargs and kwargs["json"] is not None:
        try:
            return len(json.dumps(kwargs["json"]).encode("utf-8"))
        except Exception:
            return None
    data = kwargs.get("data")
    if data is None:
        return None
    if isinstance(data, (bytes, bytearray)):
        return len(data)
    if isinstance(data, str):
        return len(data.encode("utf-8"))
    if hasattr(data, "tell") and hasattr(data, "seek"):
        try:
            pos = data.tell()
            data.seek(0, 2)
            length = data.tell()
            data.seek(pos, 0)
            return length
        except Exception:
            return None
    return None


def _body_snapshot_from_kwargs(kwargs: Mapping[str, Any]) -> Any:
    if "json" in kwargs and kwargs["json"] is not None:
        return redact(kwargs["json"])
    data = kwargs.get("data")
    if data is None:
        return None
    if isinstance(data, (bytes, bytearray)):
        length = len(data)
        if length > MAX_FIELD_BYTES:
            return {"bytes": length}
        try:
            return data.decode("utf-8", "ignore")
        except Exception:
            return {"bytes": length}
    if isinstance(data, str):
        return _truncate(data, MAX_FIELD_BYTES // 2)
    if isinstance(data, Mapping):
        return redact(data)
    if isinstance(data, Sequence):
        return [_truncate(str(item), 256) for item in list(data)[:10]]
    return str(type(data))


def _response_size(response: Any, streamed: bool) -> int | None:
    if response is None:
        return None
    try:
        header_len = response.headers.get("Content-Length")
        if header_len:
            return int(header_len)
    except Exception:
        pass
    if streamed:
        return None
    try:
        content = response.content
        if content is not None:
            return len(content)
    except Exception:
        return None
    return None


def _build_client_meta(
    method: str, url: str, kwargs: Mapping[str, Any]
) -> MutableMapping[str, Any]:
    parsed = urlparse(url)
    meta: MutableMapping[str, Any] = {
        "direction": "outbound",
        "scheme": parsed.scheme,
        "host": parsed.netloc,
        "path": parsed.path or "/",
        "query": _truncate(parsed.query, 1024),
        "request_headers": _sanitize_headers(kwargs.get("headers")),
    }
    body_snapshot = _body_snapshot_from_kwargs(kwargs)
    if body_snapshot is not None:
        meta["request_body"] = body_snapshot
    if kwargs.get("timeout") is not None:
        meta["timeout"] = kwargs["timeout"]
    if kwargs.get("stream"):
        meta["stream"] = True
    meta["verify_ssl"] = kwargs.get("verify", True)
    return meta


def _log_client_event(
    *,
    level: str,
    method: str,
    url: str,
    status: int | None,
    duration_ms: int | None,
    bytes_out: int | None,
    bytes_in: int | None,
    trace_id: str | None,
    meta: Mapping[str, Any],
    error: str | None = None,
) -> None:
    log_event(
        level,
        "traffic.http.client",
        trace=trace_id,
        method=method.upper(),
        path=url,
        status=status,
        duration_ms=duration_ms,
        bytes_out=bytes_out,
        bytes_in=bytes_in,
        component="backend.http",
        error=error,
        meta=meta,
    )


def install_requests_logging() -> None:
    """Patch ``requests.Session.request`` to emit structured traffic events."""

    global _requests_patched
    if _requests_patched:
        return

    try:
        import requests
    except Exception:  # pragma: no cover - requests not installed
        return

    original_request = requests.Session.request

    @functools.wraps(original_request)
    def _wrapped_request(self, method, url, *args, **kwargs):  # type: ignore[override]
        trace_id = _current_trace_id()
        sampled = _should_sample()
        bytes_out = _body_length_from_kwargs(kwargs)
        meta = _build_client_meta(method, url, kwargs)
        start = time.perf_counter()
        stream = bool(kwargs.get("stream"))
        try:
            response = original_request(self, method, url, *args, **kwargs)
        except Exception as exc:
            duration = int((time.perf_counter() - start) * 1000)
            if sampled:
                _log_client_event(
                    level="ERROR",
                    method=method,
                    url=url,
                    status=None,
                    duration_ms=duration,
                    bytes_out=bytes_out,
                    bytes_in=None,
                    trace_id=trace_id,
                    meta=meta,
                    error=str(exc),
                )
            raise

        duration = int((time.perf_counter() - start) * 1000)
        if sampled:
            try:
                response_meta = dict(meta)
                response_meta["status_text"] = getattr(response, "reason", None)
                response_meta["response_headers"] = _sanitize_headers(response.headers)
            except Exception:
                response_meta = meta
            _log_client_event(
                level="INFO",
                method=method,
                url=url,
                status=getattr(response, "status_code", None),
                duration_ms=duration,
                bytes_out=bytes_out,
                bytes_in=_response_size(response, stream),
                trace_id=trace_id,
                meta=response_meta,
                error=None,
            )
        return response

    requests.Session.request = _wrapped_request  # type: ignore[assignment]
    _requests_patched = True


__all__ = ["install_requests_logging", "log_inbound_http_traffic"]
