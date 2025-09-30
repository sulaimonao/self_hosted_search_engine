"""Structured logging adapter for backend telemetry events."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, MutableMapping

from backend.logging_utils import event_base, write_event

# Keys expected at the top level of emitted events.
_TOP_LEVEL_FIELDS = {
    "event",
    "level",
    "msg",
    "trace_id",
    "trace",
    "request_id",
    "session_id",
    "user_id",
    "method",
    "path",
    "status",
    "code",
    "model",
    "attempt",
    "bytes_in",
    "bytes_out",
    "duration_ms",
    "fallback_used",
    "error",
    "error_msg",
}

# Input aliases translated to the canonical field names above.
_FIELD_ALIASES = {
    "trace": "trace_id",
    "session": "session_id",
    "user": "user_id",
}


def _should_treat_as_meta(value: Any) -> bool:
    """Return True when ``value`` is better stored inside ``meta``."""

    if isinstance(value, Mapping):
        return True
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return True
    return False


def log_event(
    level: str,
    event: str,
    *,
    trace: str | None = None,
    msg: str | None = None,
    meta: Mapping[str, Any] | None = None,
    **kwargs: Any,
) -> None:
    """Emit a structured event to the shared telemetry log.

    Parameters mirror existing call-sites: ``trace`` is stored alongside the
    request and trace identifiers, ``msg`` sets the free-form message, and any
    additional keyword arguments land either at the top level (scalar values)
    or within the ``meta`` payload (for structured data).
    """

    payload: MutableMapping[str, Any] = event_base(level=level, event=event)

    if trace:
        payload["trace_id"] = trace
        payload.setdefault("trace", trace)
        payload.setdefault("request_id", trace)

    if msg is not None:
        payload["msg"] = msg

    meta_payload: dict[str, Any] = {}
    if meta:
        meta_payload.update({str(k): v for k, v in meta.items()})

    for raw_key, value in kwargs.items():
        key = _FIELD_ALIASES.get(raw_key, raw_key)
        if key in _TOP_LEVEL_FIELDS and not _should_treat_as_meta(value):
            payload[key] = value
            if key == "trace_id":
                payload.setdefault("trace", value)
                payload.setdefault("request_id", value)
        else:
            meta_payload[str(key)] = value

    if meta_payload:
        payload["meta"] = meta_payload

    write_event(dict(payload))


__all__ = ["log_event"]
