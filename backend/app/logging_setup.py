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


def _log_dir() -> Path:
    resolved = Path(os.getenv("LOG_DIR", _DEFAULT_LOG_DIR))
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def _resolve_level() -> int:
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    return getattr(logging, level_name, logging.INFO)


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
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, datefmt="%Y-%m-%d %H:%M:%S"),
            "level": record.levelname.lower(),
            "component": getattr(record, "component", "flask-api"),
            "correlation_id": getattr(record, "correlation_id", None),
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["stack"] = self.formatException(record.exc_info)
        meta = getattr(record, "meta", None)
        if meta:
            payload["meta"] = meta
        return json.dumps(payload, ensure_ascii=False)


def _plain_formatter() -> logging.Formatter:
    return logging.Formatter(
        "%(asctime)s [%(levelname)s] %(correlation_id)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


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
