"""SQLite-backed frontier queue used by the deep-research agent."""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping


_SCHEMA = """
CREATE TABLE IF NOT EXISTS frontier_queue (
    url TEXT PRIMARY KEY,
    priority REAL DEFAULT 0.0,
    status TEXT DEFAULT 'queued',
    created_at REAL DEFAULT (strftime('%s', 'now')),
    updated_at REAL DEFAULT (strftime('%s', 'now')),
    source_task_id TEXT,
    topic TEXT,
    reason TEXT,
    attempts INTEGER DEFAULT 0
);
"""


@dataclass(slots=True)
class FrontierStats:
    queued: int
    in_progress: int
    completed: int
    updated_at: float


class FrontierStore:
    """Persist crawl tasks with lightweight deduplication."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute(_SCHEMA)

    def enqueue(
        self,
        url: str,
        *,
        priority: float = 0.0,
        topic: str | None = None,
        reason: str | None = None,
        source_task_id: str | None = None,
    ) -> bool:
        sanitized = (url or "").strip()
        if not sanitized:
            raise ValueError("url must be provided")
        now = time.time()
        with sqlite3.connect(self.path) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            cursor = conn.execute(
                """
                INSERT INTO frontier_queue (url, priority, topic, reason, source_task_id, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 'queued', ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                    priority=excluded.priority,
                    topic=COALESCE(excluded.topic, frontier_queue.topic),
                    reason=COALESCE(excluded.reason, frontier_queue.reason),
                    source_task_id=COALESCE(excluded.source_task_id, frontier_queue.source_task_id),
                    status='queued',
                    updated_at=excluded.updated_at
                """,
                (
                    sanitized,
                    float(priority),
                    topic,
                    reason,
                    source_task_id,
                    now,
                    now,
                ),
            )
            conn.commit()
            return cursor.rowcount > 0

    def mark_completed(self, url: str) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                "UPDATE frontier_queue SET status='done', updated_at=strftime('%s','now') WHERE url=?",
                (url,),
            )
            conn.commit()

    def stats(self) -> FrontierStats:
        with sqlite3.connect(self.path) as conn:
            cursor = conn.execute(
                """
                SELECT
                    SUM(CASE WHEN status='queued' THEN 1 ELSE 0 END) AS queued,
                    SUM(CASE WHEN status='in_progress' THEN 1 ELSE 0 END) AS in_progress,
                    SUM(CASE WHEN status='done' THEN 1 ELSE 0 END) AS completed,
                    MAX(updated_at) AS updated_at
                FROM frontier_queue
                """
            )
            row = cursor.fetchone()
        queued = int(row[0] or 0)
        in_progress = int(row[1] or 0)
        completed = int(row[2] or 0)
        updated_at = float(row[3] or 0.0)
        return FrontierStats(queued=queued, in_progress=in_progress, completed=completed, updated_at=updated_at)

    def iter_urls(self) -> Iterable[str]:
        with sqlite3.connect(self.path) as conn:
            for (url,) in conn.execute(
                "SELECT url FROM frontier_queue WHERE status='queued' ORDER BY priority DESC, created_at ASC"
            ):
                yield url

    def to_dict(self) -> Mapping[str, int | float]:
        stats = self.stats()
        return {
            "queued": stats.queued,
            "in_progress": stats.in_progress,
            "completed": stats.completed,
            "last_updated": stats.updated_at,
        }


__all__ = ["FrontierStore", "FrontierStats"]
