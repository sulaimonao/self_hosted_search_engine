from __future__ import annotations

import sqlite3
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Optional

from crawler.utils import normalize_url, url_domain


@dataclass
class FrontierEntry:
    url: str
    depth: int
    domain: str
    use_js: bool


class FrontierDB:
    def __init__(self, path: Path, per_domain_cap: int, max_total: int):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.per_domain_cap = per_domain_cap
        self.max_total = max_total
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        cur = self._conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS urls (
                url TEXT PRIMARY KEY,
                depth INTEGER,
                enqueued_at TEXT DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'pending',
                last_error TEXT,
                domain TEXT,
                use_js INTEGER DEFAULT 0,
                tries INTEGER DEFAULT 0
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_urls_status ON urls(status)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_urls_domain ON urls(domain)")
        self._conn.commit()

    def reset_in_progress(self) -> None:
        self._conn.execute("UPDATE urls SET status='pending' WHERE status='in_progress'")
        self._conn.commit()

    def enqueue_many(self, urls: Iterable[tuple[str, int]]) -> int:
        inserted = 0
        for url, depth in urls:
            inserted += self.enqueue(url, depth)
        return inserted

    def enqueue(self, url: str, depth: int, use_js: bool = False) -> int:
        normalized = normalize_url(url)
        domain = url_domain(normalized)
        cur = self._conn.cursor()
        cur.execute("SELECT status, use_js FROM urls WHERE url=?", (normalized,))
        row = cur.fetchone()
        if row:
            status = row["status"]
            current_js = bool(row["use_js"])
            if use_js and not current_js:
                cur.execute(
                    "UPDATE urls SET use_js=1, status='pending', enqueued_at=CURRENT_TIMESTAMP WHERE url=?",
                    (normalized,),
                )
                self._conn.commit()
                return 1
            if status in {"failed", "fetched"} and use_js and not current_js:
                cur.execute(
                    "UPDATE urls SET use_js=1, status='pending', enqueued_at=CURRENT_TIMESTAMP WHERE url=?",
                    (normalized,),
                )
                self._conn.commit()
                return 1
            return 0
        if self.per_domain_cap and self._domain_count(domain) >= self.per_domain_cap:
            return 0
        if self.max_total and self._total_count() >= self.max_total:
            return 0
        cur.execute(
            "INSERT INTO urls(url, depth, domain, use_js) VALUES (?, ?, ?, ?)",
            (normalized, depth, domain, int(use_js)),
        )
        self._conn.commit()
        return 1

    def _domain_count(self, domain: str) -> int:
        cur = self._conn.execute(
            "SELECT COUNT(*) FROM urls WHERE domain=? AND status IN ('pending','in_progress','fetched')",
            (domain,),
        )
        return cur.fetchone()[0]

    def _total_count(self) -> int:
        cur = self._conn.execute("SELECT COUNT(*) FROM urls")
        return cur.fetchone()[0]

    def next_entries(self, limit: int) -> Iterator[FrontierEntry]:
        cur = self._conn.cursor()
        rows = cur.execute(
            "SELECT url, depth, domain, use_js FROM urls WHERE status='pending' ORDER BY enqueued_at ASC LIMIT ?",
            (limit,),
        ).fetchall()
        for row in rows:
            cur.execute("UPDATE urls SET status='in_progress', tries=tries+1 WHERE url=?", (row["url"],))
        self._conn.commit()
        for row in rows:
            yield FrontierEntry(url=row["url"], depth=row["depth"], domain=row["domain"], use_js=bool(row["use_js"]))

    def mark_fetched(self, url: str) -> None:
        self._conn.execute(
            "UPDATE urls SET status='fetched', last_error=NULL WHERE url=?",
            (normalize_url(url),),
        )
        self._conn.commit()

    def mark_failed(self, url: str, error: str) -> None:
        self._conn.execute(
            "UPDATE urls SET status='failed', last_error=? WHERE url=?",
            (error[:512], normalize_url(url)),
        )
        self._conn.commit()

    def stats(self) -> dict[str, int]:
        cur = self._conn.execute(
            "SELECT status, COUNT(*) as c FROM urls GROUP BY status"
        )
        counts = Counter({row["status"]: row["c"] for row in cur.fetchall()})
        return {
            "total": self._total_count(),
            "pending": counts.get("pending", 0),
            "in_progress": counts.get("in_progress", 0),
            "fetched": counts.get("fetched", 0),
            "failed": counts.get("failed", 0),
        }

    def distinct_domains(self) -> set[str]:
        cur = self._conn.execute("SELECT DISTINCT domain FROM urls WHERE domain IS NOT NULL")
        return {row[0] for row in cur.fetchall() if row[0]}

    def clear(self) -> None:
        self._conn.execute("DELETE FROM urls")
        self._conn.commit()

    def iter_all(self) -> Iterator[sqlite3.Row]:
        cur = self._conn.execute(
            "SELECT url, depth, status, domain, use_js FROM urls ORDER BY enqueued_at"
        )
        for row in cur:
            yield row

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "FrontierDB":
        return self

    def __exit__(self, exc_type, exc, tb) -> Optional[bool]:
        self.close()
        return None
