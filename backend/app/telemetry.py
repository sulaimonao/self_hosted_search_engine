"""Lightweight telemetry shim with optional local logging."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Mapping

__all__ = ["capture"]

_LOGGER = logging.getLogger(__name__)
_LOG_PATH = Path("/tmp/telemetry.log")
_LOG_LOCK = Lock()

_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}
_DEV_ENVS = {"development", "dev", "local"}


def _normalize_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    lowered = value.strip().lower()
    if lowered in _TRUE_VALUES:
        return True
    if lowered in _FALSE_VALUES:
        return False
    return None


def _app_env() -> str:
    env = os.getenv("APP_ENV", "development").strip()
    return env or "development"


def _is_dev() -> bool:
    return _app_env().lower() in _DEV_ENVS


def _telemetry_enabled() -> bool:
    override = _normalize_bool(os.getenv("TELEMETRY_ENABLED"))
    if override is not None:
        return override
    return not _is_dev()


def _should_log_local() -> bool:
    return bool(_normalize_bool(os.getenv("TELEMETRY_LOG_LOCAL")))


def _merge_properties(
    props: Mapping[str, Any] | None, extra: Mapping[str, Any]
) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    if props:
        for key, value in props.items():
            if isinstance(key, str) and key:
                merged[key] = value
    for key, value in extra.items():
        if isinstance(key, str) and key:
            merged[key] = value
    return merged


def _write_local_log(event: str, properties: Mapping[str, Any]) -> None:
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "properties": dict(properties),
    }
    line = json.dumps(payload, ensure_ascii=False)
    with _LOG_LOCK:
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")


def _emit_event(event: str, properties: Mapping[str, Any]) -> None:
    """Hook for dispatching telemetry to a remote backend.

    The default implementation is a no-op so deployments without
    telemetry dependencies stay silent. Tests or runtime code can
    monkeypatch this function to integrate with a real provider.
    """


def capture(
    event_name: str, props: Mapping[str, Any] | None = None, **kwargs: Any
) -> bool:
    """Record a telemetry event if enabled.

    Returns ``True`` when the event was processed (either dispatched
    remotely or logged locally). Always swallows errors when running in
    development to avoid noisy stack traces.
    """

    if not isinstance(event_name, str):
        return False
    event = event_name.strip()
    if not event:
        return False

    properties = _merge_properties(props, kwargs)

    should_log = _should_log_local()
    enabled = _telemetry_enabled()

    if not should_log and not enabled:
        return False

    try:
        if should_log:
            _write_local_log(event, properties)
        if enabled:
            _emit_event(event, properties)
        return True
    except Exception:  # pragma: no cover - defensive logging path
        if _is_dev():
            return False
        _LOGGER.warning("Failed to capture telemetry event '%s'", event, exc_info=True)
        return False
