"""Lightweight telemetry helpers used throughout the backend."""

from __future__ import annotations

from __future__ import annotations

from typing import Any, Mapping

from backend.telemetry import event as _event


def capture(event_name: str, props: Mapping[str, Any] | None = None, **kwargs: Any) -> bool:
    """Capture a telemetry event using the shared agent logger."""

    if not event_name:
        return False
    payload: dict[str, Any] = dict(props or {})
    payload.update({str(k): v for k, v in kwargs.items()})
    _event(event_name, payload)
    return True


__all__ = ["capture"]
