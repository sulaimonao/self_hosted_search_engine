import logging
LOG_MAX_BYTES = int(os.getenv("LOG_MAX_BYTES", "10485760"))
LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", "7"))
try:
    from concurrent_log_handler import ConcurrentRotatingFileHandler
    _CONCURRENT_LOG_HANDLER_AVAILABLE = True
except ImportError:
    ConcurrentRotatingFileHandler = None
    _CONCURRENT_LOG_HANDLER_AVAILABLE = False
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
LOG_SPLIT_BY_FEATURE = os.getenv("LOG_SPLIT_BY_FEATURE", "1").lower() in {"1", "true", "yes", "on"}
LOG_ROTATE_DAILY = os.getenv("LOG_ROTATE_DAILY", "1").lower() in {"1", "true", "yes", "on"}
LOG_SAMPLE_PCT = float(os.getenv("LOG_SAMPLE_PCT", "1.0"))  # 0..1

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

    # Optionally mirror to a per-feature file to keep files smaller and easier to scan
    if LOG_SPLIT_BY_FEATURE:
        try:
            event_name = str(ev.get("event") or "").strip()
            feature = str(ev.get("feature") or ev.get("feat") or "").strip()
            if not feature:
                # derive from event prefix, e.g., "chat.stream_summary" -> "chat"
                if "." in event_name:
                    feature = event_name.split(".", 1)[0]
                elif event_name:
                    feature = event_name
                else:
                    feature = "app"
            feature_dir = os.path.join(LOG_DIR, feature)
            os.makedirs(feature_dir, exist_ok=True)
            if LOG_ROTATE_DAILY:
                # daily file naming: YYYY-MM-DD.ndjson
                day = datetime.now(timezone.utc).date().isoformat()
                per_path = os.path.join(feature_dir, f"{day}.ndjson")
            else:
                per_path = os.path.join(feature_dir, "events.ndjson")
            if _CONCURRENT_LOG_HANDLER_AVAILABLE:
                handler = ConcurrentRotatingFileHandler(
                    per_path,
                    maxBytes=LOG_MAX_BYTES if not LOG_ROTATE_DAILY else 0,
                    backupCount=LOG_BACKUP_COUNT,
                    encoding="utf-8"
                )
                handler.setFormatter(logging.Formatter("%(message)s"))
                record = logging.LogRecord(
                    name=feature,
                    level=logging.INFO,
                    pathname=__file__,
                    lineno=0,
                    msg=line,
                    args=(),
                    exc_info=None
                )
                handler.emit(record)
                handler.close()
            else:
                with _lock:
                    with io.open(per_path, "a", encoding="utf-8") as fh:
                        fh.write(line + "\n")
        except Exception:
            # best-effort mirror; never raise
            pass


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
    # sampling (best-effort) to reduce growth under heavy load
    try:
        if LOG_SAMPLE_PCT < 1.0:
            import random

            pct = max(0.0, min(1.0, LOG_SAMPLE_PCT))
            if pct <= 0.0 or random.random() >= pct:
                return
    except Exception:
        # ignore sampling errors
        pass

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
