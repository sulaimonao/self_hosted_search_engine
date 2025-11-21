"""Centralized Flask logging configuration with rotation and JSONL output."""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
from pathlib import Path
from typing import Any, Optional

from flask import g, has_request_context, request


_LOG_CONFIGURED = False
_REQUEST_LOGGER_NAME = "flask.api"
_ROOT_DIR = Path(__file__).resolve().parents[2]
_DEFAULT_LOG_DIR = _ROOT_DIR / "logs"
_DEFAULT_COMPONENT = os.getenv("LOG_COMPONENT", "flask-api")
_MAX_MESSAGE_LENGTH = int(os.getenv("LOG_MAX_MESSAGE_LENGTH", "2000"))
_MAX_STACK_LENGTH = int(os.getenv("LOG_MAX_STACK_LENGTH", "8000"))


def _log_dir() -> Path:
    resolved = Path(os.getenv("LOG_DIR", _DEFAULT_LOG_DIR))
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def _resolve_level() -> int:
    explicit = os.getenv("LOG_LEVEL")
    if explicit:
        level_name = explicit.upper()
    else:
        level_name = "DEBUG" if _is_dev_environment() else "INFO"
    return getattr(logging, level_name, logging.INFO)


def _is_dev_environment() -> bool:
    for key in ("FLASK_ENV", "APP_ENV", "ENV", "NODE_ENV"):
        value = os.getenv(key)
        if not value:
            continue
        normalized = value.strip().lower()
        if normalized in {"dev", "development", "local"}:
            return True
        if normalized in {"prod", "production"}:
            return False
    flask_debug = os.getenv("FLASK_DEBUG")
    if flask_debug and flask_debug not in {"0", "false", "False"}:
        return True
    return False


def _truncate(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    if limit <= 0 or len(value) <= limit:
        return value
    suffix = f"…[truncated {len(value) - limit} chars]"
    return f"{value[:limit]}{suffix}"


def _resolve_event(record: logging.LogRecord) -> str:
    for attr in ("event", "event_name", "eventName"):
        value = getattr(record, attr, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    meta = getattr(record, "meta", None)
    if isinstance(meta, dict):
        event = meta.get("event")
        if isinstance(event, str) and event.strip():
            return event.strip()
    return "log"


def _safe_meta(record: logging.LogRecord) -> Optional[dict[str, Any]]:
    meta = getattr(record, "meta", None)
    if meta is None:
        return None
    if isinstance(meta, dict):
        try:
            json.dumps(meta)
            return meta
        except TypeError:
            return {"repr": repr(meta)}
    return {"value": repr(meta)}


class CorrelationIdFilter(logging.Filter):
    """Ensures every log record carries a correlation_id attribute."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D401 - standard signature
        if getattr(record, "correlation_id", None):
            return True
        correlation_id: Optional[str] = None
        if has_request_context():
            correlation_id = (
                request.headers.get("X-Correlation-Id")
                or getattr(g, "correlation_id", None)
                or getattr(g, "trace_id", None)
            )
        record.correlation_id = correlation_id
        return True


class JsonlFormatter(logging.Formatter):
    """Formatter that renders each record as a single JSON object."""

    def format(self, record: logging.LogRecord) -> str:  # noqa: D401 - override signature
        message = record.getMessage()
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, datefmt="%Y-%m-%d %H:%M:%S"),
            "level": record.levelname.lower(),
            "component": getattr(record, "component", _DEFAULT_COMPONENT),
            "correlation_id": getattr(record, "correlation_id", None),
            "event": _resolve_event(record),
            "message": _truncate(message, _MAX_MESSAGE_LENGTH),
        }
        if record.exc_info:
            payload["stack"] = _truncate(self.formatException(record.exc_info), _MAX_STACK_LENGTH)
        meta = _safe_meta(record)
        if meta:
            payload["meta"] = meta
        return json.dumps(payload, ensure_ascii=False)


class PlainFormatter(logging.Formatter):
    """Formatter used for the human-readable rotating log."""

    def format(self, record: logging.LogRecord) -> str:  # noqa: D401 - override signature
        timestamp = self.formatTime(record, datefmt="%Y-%m-%d %H:%M:%S")
        component = getattr(record, "component", _DEFAULT_COMPONENT)
        correlation_id = getattr(record, "correlation_id", None)
        event_name = _resolve_event(record)
        message = record.getMessage()
        rendered_message = _truncate(message, _MAX_MESSAGE_LENGTH)
        if record.exc_info:
            rendered_message = _truncate(self.formatException(record.exc_info), _MAX_STACK_LENGTH)
        parts = [timestamp, f"[{record.levelname}]", f"({component})"]
        if correlation_id:
            parts.append(f"cid={correlation_id}")
        if event_name:
            parts.append(f"evt={event_name}")
        meta = _safe_meta(record)
        if meta:
            return f"{' '.join(parts)} {rendered_message} {json.dumps(meta, ensure_ascii=False)}"
        return f"{' '.join(parts)} {rendered_message}"


def _plain_formatter() -> logging.Formatter:
    return PlainFormatter()


def _build_namer(extension: str):
    def _rename(default_name: str) -> str:
        path = Path(default_name)
        parts = path.name.split(".")
        if len(parts) >= 3:
            base = parts[0]
            date_part = parts[-1]
            return str(path.with_name(f"{base}-{date_part}.{extension}"))
        return str(path)

    return _rename


def _build_plain_handler(level: int) -> logging.Handler:
    handler = logging.handlers.TimedRotatingFileHandler(
        filename=_log_dir() / "flask.log",
        when="midnight",
        interval=1,
        backupCount=14,
        encoding="utf-8",
    )
    handler.suffix = "%Y-%m-%d"
    handler.namer = _build_namer("log")
    handler.setLevel(level)
    handler.setFormatter(_plain_formatter())
    handler.addFilter(CorrelationIdFilter())
    return handler


def _build_jsonl_handler(level: int) -> logging.Handler:
    handler = logging.handlers.TimedRotatingFileHandler(
        filename=_log_dir() / "flask.jsonl",
        when="midnight",
        interval=1,
        backupCount=14,
        encoding="utf-8",
    )
    handler.suffix = "%Y-%m-%d"
    handler.namer = _build_namer("jsonl")
    handler.setLevel(level)
    handler.setFormatter(JsonlFormatter())
    handler.addFilter(CorrelationIdFilter())
    return handler


def setup_logging() -> None:
    """Initialize the backend logging stack exactly once."""

    global _LOG_CONFIGURED
    if _LOG_CONFIGURED:
        return

    level = _resolve_level()
    plain_handler = _build_plain_handler(level)
    jsonl_handler = _build_jsonl_handler(level)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers = [plain_handler, jsonl_handler]

    logging.captureWarnings(True)

    request_logger = logging.getLogger(_REQUEST_LOGGER_NAME)
    request_logger.setLevel(level)

    _LOG_CONFIGURED = True


def get_request_logger() -> logging.Logger:
    """Return the logger used for per-request summaries."""

    setup_logging()
    return logging.getLogger(_REQUEST_LOGGER_NAME)


__all__ = ["setup_logging", "get_request_logger"]
