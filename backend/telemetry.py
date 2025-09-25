"""Local telemetry event logging for the agent runtime."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

DEFAULT_PATH = Path(os.getenv("TELEMETRY_EVENTS_PATH", "data/telemetry/events.ndjson"))


def _target_path() -> Path:
    override = os.getenv("TELEMETRY_EVENTS_PATH")
    return Path(override) if override else DEFAULT_PATH


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def event(name: str, properties: Mapping[str, Any] | None = None, **extra: Any) -> Path:
    """Append a structured telemetry event to the local log.

    Parameters
    ----------
    name:
        Event name.
    properties:
        Optional mapping of key/value pairs to include.
    extra:
        Additional keyword arguments merged into ``properties``.

    Returns
    -------
    Path
        Location of the event log file for observability.
    """

    payload: dict[str, Any] = {
        "event": str(name),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    merged: dict[str, Any] = {}
    if properties:
        merged.update({str(k): v for k, v in properties.items()})
    if extra:
        merged.update({str(k): v for k, v in extra.items()})
    if merged:
        payload["properties"] = merged
    log_path = _target_path()
    _ensure_parent(log_path)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return log_path


__all__ = ["DEFAULT_PATH", "event"]
