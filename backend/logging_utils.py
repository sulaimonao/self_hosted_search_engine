"""Structured logging helpers for telemetry events and redaction."""

from __future__ import annotations

import hashlib
import io
import json
import os
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional

LOG_DIR = os.getenv("LOG_DIR", "data/telemetry")
LOG_PATH = os.path.join(LOG_DIR, "events.ndjson")
MAX_FIELD_BYTES = int(os.getenv("LOG_MAX_FIELD_BYTES", "4096"))

SENSITIVE_KEYS = {
    "authorization",
    "cookie",
    "set-cookie",
    "password",
    "token",
    "api_key",
    "secret",
    "access-token",
    "refresh-token",
}
NOISY_KEYS = {"html", "body", "content", "text", "embedding", "stack"}

os.makedirs(LOG_DIR, exist_ok=True)

_lock = threading.Lock()

try:
    from opentelemetry import trace  # type: ignore
    from opentelemetry.sdk.trace import TracerProvider  # type: ignore
    from opentelemetry.sdk.trace.export import (  # type: ignore
        BatchSpanProcessor,
        OTLPSpanExporter,
    )
except Exception:  # pragma: no cover - optional dependency
    trace = None  # type: ignore
    TracerProvider = None  # type: ignore
    BatchSpanProcessor = None  # type: ignore
    OTLPSpanExporter = None  # type: ignore

_OTEL_TRACER = None
_OTEL_ENABLED = bool(os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"))

if _OTEL_ENABLED and trace and TracerProvider and BatchSpanProcessor and OTLPSpanExporter:
    try:  # pragma: no cover - exercised only when OTEL deps installed
        provider = TracerProvider()
        trace.set_tracer_provider(provider)
        endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
        insecure = os.getenv("OTEL_EXPORTER_OTLP_INSECURE", "true").lower() == "true"
        headers_env = os.getenv("OTEL_EXPORTER_OTLP_HEADERS", "")
        headers: Optional[Dict[str, str]] = None
        if headers_env:
            headers = {}
            for pair in headers_env.split(","):
                if not pair or "=" not in pair:
                    continue
                key, value = pair.split("=", 1)
                headers[key.strip()] = value.strip()
        exporter = OTLPSpanExporter(
            endpoint=endpoint,
            insecure=insecure,
            headers=headers,
        )
        processor = BatchSpanProcessor(exporter)
        provider.add_span_processor(processor)
        _OTEL_TRACER = trace.get_tracer("self_hosted_search_engine.telemetry")
    except Exception:  # pragma: no cover - defensive fallback
        _OTEL_TRACER = None


def now_iso() -> str:
    """Return the current UTC timestamp in ISO-8601 with millisecond precision."""

    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", "ignore")).hexdigest()


def redact(obj: Any) -> Any:
    """Recursively redact sensitive or noisy payload values."""

    if obj is None:
        return None
    if isinstance(obj, (int, float, bool)):
        return obj
    if isinstance(obj, str):
        if len(obj.encode("utf-8", "ignore")) > MAX_FIELD_BYTES:
            return {
                "sha256": _sha256(obj),
                "preview": obj[:256] + "...[truncated]",
            }
        return obj
    if isinstance(obj, dict):
        out: Dict[str, Any] = {}
        for k, v in obj.items():
            lk = str(k).lower()
            if lk in SENSITIVE_KEYS:
                out[k] = "[REDACTED]"
                continue
            if lk in NOISY_KEYS:
                if isinstance(v, str):
                    out[k] = {"sha256": _sha256(v), "len": len(v)}
                else:
                    out[k] = "[REDACTED_NOISY]"
                continue
            out[k] = redact(v)
        return out
    if isinstance(obj, (list, tuple, set)):
        return [redact(x) for x in obj]
    return str(obj)


def event_base(**kv: Any) -> Dict[str, Any]:
    base = {
        "level": kv.pop("level", "INFO"),
        "event": kv.pop("event", "log"),
        "service": "self_hosted_search_engine",
        "version": "1.0.0",
    }
    base.update(kv)
    return base


def new_request_id() -> str:
    return "req_" + uuid.uuid4().hex[:10]


def _emit_console(ev: Dict[str, Any]) -> None:
    lvl = ev.get("level", "INFO")
    event = ev.get("event", "log")
    msg = ev.get("msg", "")
    sys.stdout.write(f"[{lvl}] {event} {msg}\n")


def _emit_file(ev: Dict[str, Any]) -> None:
    line = json.dumps(ev, ensure_ascii=False)
    with _lock:
        with io.open(LOG_PATH, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")


def _emit_otel(ev: Dict[str, Any]) -> None:
    if not _OTEL_TRACER:
        return
    try:  # pragma: no cover - depends on optional otel runtime
        span_name = ev.get("event") or "log"
        attributes: Iterable[tuple[str, Any]] = []
        meta = ev.get("meta") if isinstance(ev.get("meta"), dict) else None
        attribute_items = {
            "service.name": ev.get("service"),
            "log.level": ev.get("level"),
            "request.id": ev.get("request_id"),
            "session.id": ev.get("session_id"),
            "user.id": ev.get("user_id"),
            "log.event": ev.get("event"),
            "log.msg": ev.get("msg"),
        }
        if meta:
            for key, value in meta.items():
                attribute_items[f"meta.{key}"] = value
        attributes = attribute_items.items()
        with _OTEL_TRACER.start_as_current_span(span_name) as span:
            for key, value in attributes:
                if value is None:
                    continue
                span.set_attribute(key, value)
    except Exception:
        pass


def write_event(ev: Dict[str, Any]) -> None:
    ev.setdefault("ts", now_iso())
    if "duration_ms" in ev and isinstance(ev["duration_ms"], float):
        ev["duration_ms"] = int(ev["duration_ms"])
    if "meta" in ev:
        ev["meta"] = redact(ev["meta"])
    try:
        _emit_file(ev)
    except Exception:  # pragma: no cover - best-effort logging
        pass
    try:
        _emit_console(ev)
    except Exception:
        pass
    if _OTEL_ENABLED:
        _emit_otel(ev)


__all__ = [
    "event_base",
    "new_request_id",
    "now_iso",
    "redact",
    "write_event",
]
