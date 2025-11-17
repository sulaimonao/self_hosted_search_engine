"""Utilities for importing browser history archives into the app state DB."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from backend.app.db import AppStateDB

_WINDOWS_EPOCH = datetime(1601, 1, 1, tzinfo=timezone.utc)


def _chrome_timestamp_to_iso(raw_value: int | str | None) -> str:
    if raw_value is None:
        return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")
    try:
        microseconds = int(raw_value)
    except (TypeError, ValueError):
        return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")
    timestamp = _WINDOWS_EPOCH + timedelta(microseconds=microseconds)
    return timestamp.isoformat(timespec="seconds")


@dataclass(slots=True)
class ChromeHistoryEntry:
    """Minimal representation of a Chrome/Edge history row."""

    url: str
    title: str | None
    last_visit_time: str
    referrer: str | None = None
    content_type: str | None = None
    status_code: int | None = None

    @classmethod
    def from_row(cls, row: Mapping[str, object]) -> "ChromeHistoryEntry":
        url = str(row.get("url") or "").strip()
        if not url:
            raise ValueError("history row missing URL")
        title_value = row.get("title")
        title = str(title_value).strip() or None if title_value is not None else None
        last_visit_time = _chrome_timestamp_to_iso(row.get("last_visit_time"))
        referrer_value = row.get("referrer") or row.get("referringVisitUrl")
        referrer = str(referrer_value).strip() or None if referrer_value else None
        mime_value = row.get("content_type") or row.get("mime_type")
        mime_type = str(mime_value).strip() or None if mime_value else None
        status = row.get("status_code") or row.get("http_status")
        status_code = None
        if status is not None:
            try:
                status_code = int(status)
            except (TypeError, ValueError):
                status_code = None
        return cls(
            url=url,
            title=title,
            last_visit_time=last_visit_time,
            referrer=referrer,
            content_type=mime_type,
            status_code=status_code,
        )

    def to_record(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "url": self.url,
            "title": self.title,
            "visited_at": self.last_visit_time,
        }
        if self.referrer:
            payload["referrer"] = self.referrer
        if self.content_type:
            payload["content_type"] = self.content_type
        if self.status_code is not None:
            payload["status_code"] = self.status_code
        return payload


def import_chrome_history_entries(
    state_db: AppStateDB,
    entries: Iterable[Mapping[str, object]],
) -> int:
    """Import Chrome/Edge entries supplied as mappings (e.g., JSON rows)."""

    imported = 0
    for entry in entries:
        record = ChromeHistoryEntry.from_row(entry).to_record()
        state_db.import_browser_history_record(record)
        imported += 1
    return imported


def load_chrome_history_json(path: Path) -> Sequence[Mapping[str, object]]:
    """Load a Chrome/Edge history export stored as JSON lines."""

    import json

    resolved = path if path.is_absolute() else path.resolve()
    if not resolved.exists():
        raise FileNotFoundError(resolved)
    payload: list[Mapping[str, object]] = []
    with resolved.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            payload.append(json.loads(line))
    return payload
