"""Lightweight incident log used by the chat blueprint during tests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class IncidentRecord:
    kind: str
    message: str | None
    detail: dict[str, Any]


class IncidentLog:
    """In-memory incident recorder used for diagnostics."""

    def __init__(self) -> None:
        self._events: list[IncidentRecord] = []

    def record(
        self,
        kind: str,
        message: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        self._events.append(
            IncidentRecord(kind=kind, message=message, detail=detail or {}),
        )

    def recent(self, limit: int = 50) -> list[IncidentRecord]:
        return self._events[-limit:]


__all__ = ["IncidentLog", "IncidentRecord"]
