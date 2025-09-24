"""Lightweight telemetry helpers used throughout the backend."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Mapping, MutableMapping

LOGGER = logging.getLogger(__name__)
LOG_PATH = Path(os.getenv("TELEMETRY_LOG_PATH", "/tmp/telemetry.log"))


def _is_truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _is_enabled() -> bool:
    explicit = os.getenv("TELEMETRY_ENABLED")
    if explicit is not None:
        return _is_truthy(explicit)
    environment = os.getenv("APP_ENV", "development").strip().lower()
    return environment in {"production", "prod"}


def _emit_event(event_name: str, props: Mapping[str, Any]) -> None:
    """Dispatch the telemetry payload.

    The default implementation is a no-op so tests can monkeypatch the behavior.
    """


def _log_local(event_name: str, props: Mapping[str, Any]) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            payload = {"event": event_name, "properties": dict(props)}
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:  # pragma: no cover - defensive logging only
        LOGGER.debug("Unable to write telemetry log locally", exc_info=True)


def capture(
    event_name: str, props: Mapping[str, Any] | None = None, **kwargs: Any
) -> bool:
    payload: MutableMapping[str, Any] = dict(props or {})
    payload.update(kwargs)

    wrote_local = False
    if _is_truthy(os.getenv("TELEMETRY_LOG_LOCAL")):
        _log_local(event_name, payload)
        wrote_local = True

    if not _is_enabled():
        return wrote_local

    try:
        _emit_event(event_name, payload)
    except Exception:  # pragma: no cover - converted to warning for resilience
        LOGGER.warning("Failed to capture telemetry event", exc_info=True)
        return False
    return True


__all__ = ["capture", "LOG_PATH", "_emit_event"]
