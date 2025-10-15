"""SQLite persistence for the learned web graph.

This module tracks domains, pages, links, crawl executions and discovery
events produced by the focused crawl pipeline.  It provides a thin helper
class that hides SQLite plumbing while offering ergonomic helpers tailored to
the crawler and search components.
"""

from __future__ import annotations

import json
import math
import os
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Sequence

from backend.app.search.embedding import cosine_similarity
from urllib.parse import urlparse, urlunparse

__all__ = [
    "LearnedWebDB",
    "get_db",
]


_DEFAULT_DB_ENV = "LEARNED_WEB_DB_PATH"


def _normalize_host(url: str) -> Optional[str]:
    candidate = (url or "").strip()
    if not candidate:
        return None
    parsed = urlparse(candidate if "://" in candidate else f"https://{candidate}")
    host = (parsed.netloc or parsed.path or "").strip().lower()
    if not host:
        return None
    return host[4:] if host.startswith("www.") else host


def _normalize_url(url: str) -> Optional[str]:
    candidate = (url or "").strip()
    if not candidate:
        return None
    if candidate.startswith("//"):
        candidate = f"https:{candidate}"
    elif not candidate.startswith(("http://", "https://")):
        candidate = f"https://{candidate.lstrip('/')}"

    parsed = urlparse(candidate)
    if not parsed.scheme or not parsed.netloc:
        return None

    path = parsed.path or "/"
    if not path.startswith("/"):
        path = "/" + path
    if path == "/":
        normalized_path = "/"
    else:
        normalized_path = path.rstrip("/") or "/"

    normalized = parsed._replace(
        path=normalized_path,
        params="",
        fragment="",
    )
    normalized_url = urlunparse(normalized)
    if normalized_path == "/" and not parsed.query and not parsed.params:
        return normalized_url.rstrip("/")
    return normalized_url


def _ts(value: Optional[float]) -> float:
    return float(value if value is not None else time.time())


def _normalize_embedding(embedding: Sequence[float]) -> list[float]:
    vector = [float(value) for value in embedding]
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0.0:
        return [0.0 for value in vector]
    return [value / norm for value in vector]


def _serialize_embedding(embedding: Sequence[float]) -> str:
    normalized = _normalize_embedding(embedding)
    return json.dumps([round(value, 6) for value in normalized])


def _deserialize_embedding(payload: str) -> list[float]:
    try:
        data = json.loads(payload or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [float(value) for value in data]


@dataclass
class LearnedWebDB:
    """Small helper around a SQLite database storing learned web state."""

    path: Path

    def __post_init__(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            str(self.path),
            detect_types=sqlite3.PARSE_DECLTYPES,
            isolation_level=None,
            check_same_thread=False,
        )
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA foreign_keys=ON;")
        self._conn.execute("PRAGMA synchronous=NORMAL;")
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._initialize_schema()

    # -- schema -----------------------------------------------------------------

    def _initialize_schema(self) -> None:
        ddl = """
        CREATE TABLE IF NOT EXISTS domains (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            host TEXT NOT NULL UNIQUE,
            first_seen REAL NOT NULL,
            last_seen REAL NOT NULL,
            learned_score REAL NOT NULL DEFAULT 0.0,
            discovery_count INTEGER NOT NULL DEFAULT 0,
            last_discovery_reason TEXT,
            last_crawl_at REAL,
            last_index_at REAL
        );

        CREATE TABLE IF NOT EXISTS crawls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query TEXT NOT NULL,
            started_at REAL NOT NULL,
            completed_at REAL,
            pages_fetched INTEGER NOT NULL DEFAULT 0,
            docs_indexed INTEGER NOT NULL DEFAULT 0,
            budget INTEGER,
            seed_count INTEGER,
            use_llm INTEGER NOT NULL DEFAULT 0,
            model TEXT,
            raw_path TEXT
        );

        CREATE TABLE IF NOT EXISTS pages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL UNIQUE,
            domain_id INTEGER NOT NULL,
            title TEXT,
            status INTEGER,
            first_seen REAL NOT NULL,
            last_seen REAL NOT NULL,
            fetched_at REAL NOT NULL,
            indexed_at REAL,
            fingerprint_simhash INTEGER,
            fingerprint_md5 TEXT,
            crawl_id INTEGER,
            FOREIGN KEY(domain_id) REFERENCES domains(id) ON DELETE CASCADE,
            FOREIGN KEY(crawl_id) REFERENCES crawls(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_page_id INTEGER NOT NULL,
            to_url TEXT NOT NULL,
            first_seen REAL NOT NULL,
            last_seen REAL NOT NULL,
            crawl_id INTEGER,
            UNIQUE(from_page_id, to_url),
            FOREIGN KEY(from_page_id) REFERENCES pages(id) ON DELETE CASCADE,
            FOREIGN KEY(crawl_id) REFERENCES crawls(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS discoveries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query TEXT NOT NULL,
            domain_id INTEGER NOT NULL,
            url TEXT NOT NULL,
            reason TEXT NOT NULL,
            source TEXT,
            score REAL NOT NULL,
            discovered_at REAL NOT NULL,
            crawl_id INTEGER,
            FOREIGN KEY(domain_id) REFERENCES domains(id) ON DELETE CASCADE,
            FOREIGN KEY(crawl_id) REFERENCES crawls(id) ON DELETE SET NULL
        );

        CREATE INDEX IF NOT EXISTS idx_domains_last_seen ON domains(last_seen DESC);
        CREATE INDEX IF NOT EXISTS idx_domains_learned_score ON domains(learned_score DESC);
        CREATE INDEX IF NOT EXISTS idx_pages_domain_id ON pages(domain_id);
        CREATE INDEX IF NOT EXISTS idx_links_to_url ON links(to_url);
        CREATE INDEX IF NOT EXISTS idx_discoveries_query ON discoveries(query);

        CREATE TABLE IF NOT EXISTS query_embeddings (
            query TEXT PRIMARY KEY,
            embedding TEXT NOT NULL,
            updated_at REAL NOT NULL
        );
        """
        with self._lock:
            self._conn.executescript(ddl)

    # -- domain helpers ----------------------------------------------------------

    def upsert_domain(
        self,
        host: str,
        *,
        seen_at: Optional[float] = None,
        learned_score: Optional[float] = None,
        increment_discovery: bool = False,
        discovery_reason: Optional[str] = None,
        last_crawl_at: Optional[float] = None,
        last_index_at: Optional[float] = None,
    ) -> Optional[int]:
        with self._lock:
            return self._upsert_domain_locked(
                host,
                seen_at=seen_at,
                learned_score=learned_score,
                increment_discovery=increment_discovery,
                discovery_reason=discovery_reason,
                last_crawl_at=last_crawl_at,
                last_index_at=last_index_at,
            )

    def _upsert_domain_locked(
        self,
        host: str,
        *,
        seen_at: Optional[float],
        learned_score: Optional[float],
        increment_discovery: bool,
        discovery_reason: Optional[str],
        last_crawl_at: Optional[float],
        last_index_at: Optional[float],
    ) -> Optional[int]:
        normalized = _normalize_host(host)
        if not normalized:
            return None
        ts = _ts(seen_at)
        score = float(learned_score or 0.0)
        discovery_count = 1 if increment_discovery else 0
        reason = discovery_reason if increment_discovery else None
        self._conn.execute(
            """
            INSERT INTO domains (
                host,
                first_seen,
                last_seen,
                learned_score,
                discovery_count,
                last_discovery_reason,
                last_crawl_at,
                last_index_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(host) DO UPDATE SET
                last_seen = CASE
                    WHEN excluded.last_seen > domains.last_seen THEN excluded.last_seen
                    ELSE domains.last_seen
                END,
                learned_score = CASE
                    WHEN excluded.learned_score > domains.learned_score THEN excluded.learned_score
                    ELSE domains.learned_score
                END,
                discovery_count = domains.discovery_count + excluded.discovery_count,
                last_discovery_reason = CASE
                    WHEN excluded.discovery_count > 0 THEN excluded.last_discovery_reason
                    ELSE domains.last_discovery_reason
                END,
                last_crawl_at = CASE
                    WHEN excluded.last_crawl_at IS NULL THEN domains.last_crawl_at
                    WHEN domains.last_crawl_at IS NULL THEN excluded.last_crawl_at
                    WHEN excluded.last_crawl_at > domains.last_crawl_at THEN excluded.last_crawl_at
                    ELSE domains.last_crawl_at
                END,
                last_index_at = CASE
                    WHEN excluded.last_index_at IS NULL THEN domains.last_index_at
                    WHEN domains.last_index_at IS NULL THEN excluded.last_index_at
                    WHEN excluded.last_index_at > domains.last_index_at THEN excluded.last_index_at
                    ELSE domains.last_index_at
                END
            ;
            """,
            (
                normalized,
                ts,
                ts,
                score,
                discovery_count,
                reason,
                last_crawl_at,
                last_index_at,
            ),
        )
        row = self._conn.execute(
            "SELECT id FROM domains WHERE host = ?",
            (normalized,),
        ).fetchone()
        return int(row[0]) if row else None

    def domain_value_map(self) -> dict[str, float]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT host, learned_score FROM domains WHERE learned_score > 0"
            ).fetchall()
        return {str(row[0]): float(row[1]) for row in rows}

    def top_domains(self, limit: int = 50) -> list[str]:
        limit = max(0, int(limit))
        if limit == 0:
            return []
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT host FROM domains
                ORDER BY learned_score DESC, last_seen DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [str(row[0]) for row in rows]

    # -- crawl lifecycle ---------------------------------------------------------

    def start_crawl(
        self,
        query: str,
        *,
        started_at: Optional[float] = None,
        budget: Optional[int] = None,
        seed_count: Optional[int] = None,
        use_llm: bool = False,
        model: Optional[str] = None,
    ) -> int:
        ts = _ts(started_at)
        with self._lock:
            cursor = self._conn.execute(
                """
                INSERT INTO crawls (
                    query,
                    started_at,
                    budget,
                    seed_count,
                    use_llm,
                    model
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (query, ts, budget, seed_count, 1 if use_llm else 0, model),
            )
            return int(cursor.lastrowid)

    def complete_crawl(
        self,
        crawl_id: int,
        *,
        completed_at: Optional[float] = None,
        pages_fetched: int = 0,
        docs_indexed: int = 0,
        raw_path: Optional[str] = None,
    ) -> None:
        ts = _ts(completed_at)
        with self._lock:
            self._conn.execute(
                """
                UPDATE crawls
                SET completed_at = ?,
                    pages_fetched = ?,
                    docs_indexed = ?,
                    raw_path = ?
                WHERE id = ?
                """,
                (ts, int(pages_fetched), int(docs_indexed), raw_path, crawl_id),
            )

    # -- discoveries -------------------------------------------------------------

    def record_discovery(
        self,
        query: str,
        url: str,
        *,
        reason: str,
        score: float,
        source: Optional[str] = None,
        discovered_at: Optional[float] = None,
        crawl_id: Optional[int] = None,
    ) -> Optional[tuple[int, bool]]:
        normalized_url = _normalize_url(url)
        if not normalized_url:
            return None
        host = _normalize_host(normalized_url)
        if not host:
            return None
        ts = _ts(discovered_at)
        with self._lock:
            existing = self._conn.execute(
                "SELECT 1 FROM domains WHERE host = ?",
                (host,),
            ).fetchone()
            domain_id = self._upsert_domain_locked(
                host,
                seen_at=ts,
                learned_score=score,
                increment_discovery=True,
                discovery_reason=reason,
                last_crawl_at=None,
                last_index_at=None,
            )
            if domain_id is None:
                return None
            self._conn.execute(
                """
                INSERT INTO discoveries (
                    query,
                    domain_id,
                    url,
                    reason,
                    source,
                    score,
                    discovered_at,
                    crawl_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (query, domain_id, normalized_url, reason, source, float(score), ts, crawl_id),
            )
            created = existing is None
        return domain_id, created

    def upsert_query_embedding(
        self,
        query: str,
        embedding: Sequence[float],
        *,
        updated_at: Optional[float] = None,
    ) -> None:
        normalized_query = (query or "").strip()
        if not normalized_query:
            return
        serialized = _serialize_embedding(embedding)
        ts = _ts(updated_at)
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO query_embeddings (query, embedding, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(query) DO UPDATE SET
                    embedding = excluded.embedding,
                    updated_at = excluded.updated_at
                """,
                (normalized_query, serialized, ts),
            )

    def similar_discovery_seeds(
        self,
        embedding: Sequence[float],
        *,
        limit: int = 10,
        min_similarity: float = 0.35,
        per_query: int = 5,
    ) -> list[str]:
        if not embedding:
            return []
        target = _normalize_embedding(embedding)
        with self._lock:
            rows = self._conn.execute(
                "SELECT query, embedding FROM query_embeddings"
            ).fetchall()
        candidates: list[tuple[float, str]] = []
        for row in rows:
            stored = _deserialize_embedding(row["embedding"])
            if not stored or len(stored) != len(target):
                continue
            similarity = cosine_similarity(target, stored)
            if similarity >= min_similarity:
                candidates.append((similarity, row["query"]))
        candidates.sort(reverse=True)
        seeds: list[str] = []
        seen: set[str] = set()
        for similarity, query in candidates:
            with self._lock:
                urls = self._conn.execute(
                    """
                    SELECT url, MAX(score) AS best_score
                    FROM discoveries
                    WHERE query = ?
                    GROUP BY url
                    ORDER BY best_score DESC
                    LIMIT ?
                    """,
                    (query, int(per_query)),
                ).fetchall()
            for row in urls:
                url = row["url"]
                if url in seen:
                    continue
                seen.add(url)
                seeds.append(url)
                if len(seeds) >= limit:
                    return seeds
        return seeds

    # -- pages & links -----------------------------------------------------------

    def record_page(
        self,
        crawl_id: Optional[int],
        *,
        url: str,
        status: Optional[int],
        title: Optional[str],
        fetched_at: Optional[float],
        fingerprint_simhash: Optional[int] = None,
        fingerprint_md5: Optional[str] = None,
    ) -> Optional[int]:
        normalized_url = _normalize_url(url)
        if not normalized_url:
            return None
        host = _normalize_host(normalized_url)
        if not host:
            return None
        ts = _ts(fetched_at)
        domain_id = self.upsert_domain(host, last_crawl_at=ts)
        if domain_id is None:
            return None
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO pages (
                    url,
                    domain_id,
                    title,
                    status,
                    first_seen,
                    last_seen,
                    fetched_at,
                    indexed_at,
                    fingerprint_simhash,
                    fingerprint_md5,
                    crawl_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                    domain_id = excluded.domain_id,
                    title = excluded.title,
                    status = excluded.status,
                    last_seen = CASE
                        WHEN excluded.last_seen > pages.last_seen THEN excluded.last_seen
                        ELSE pages.last_seen
                    END,
                    fetched_at = excluded.fetched_at,
                    fingerprint_simhash = excluded.fingerprint_simhash,
                    fingerprint_md5 = excluded.fingerprint_md5,
                    crawl_id = excluded.crawl_id
                ;
                """,
                (
                    normalized_url,
                    domain_id,
                    title,
                    status,
                    ts,
                    ts,
                    ts,
                    fingerprint_simhash,
                    fingerprint_md5,
                    crawl_id,
                ),
            )
            row = self._conn.execute(
                "SELECT id FROM pages WHERE url = ?",
                (normalized_url,),
            ).fetchone()
        return int(row[0]) if row else None

    def record_links(
        self,
        from_page_id: int,
        links: Iterable[str],
        *,
        discovered_at: Optional[float] = None,
        crawl_id: Optional[int] = None,
    ) -> None:
        ts = _ts(discovered_at)
        payload = []
        for link in links:
            normalized = _normalize_url(link)
            if not normalized:
                continue
            payload.append((from_page_id, normalized, ts, ts, crawl_id))
        if not payload:
            return
        with self._lock:
            self._conn.executemany(
                """
                INSERT INTO links (
                    from_page_id,
                    to_url,
                    first_seen,
                    last_seen,
                    crawl_id
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(from_page_id, to_url) DO UPDATE SET
                    last_seen = CASE
                        WHEN excluded.last_seen > links.last_seen THEN excluded.last_seen
                        ELSE links.last_seen
                    END,
                    crawl_id = excluded.crawl_id
                ;
                """,
                payload,
            )

    def mark_pages_indexed(
        self,
        urls: Iterable[str],
        *,
        indexed_at: Optional[float] = None,
    ) -> None:
        ts = _ts(indexed_at)
        normalized_urls = []
        for url in urls:
            normalized = _normalize_url(url)
            if normalized:
                normalized_urls.append(normalized)
        if not normalized_urls:
            return
        with self._lock:
            for normalized in normalized_urls:
                self._conn.execute(
                    """
                    UPDATE pages
                    SET indexed_at = CASE
                            WHEN indexed_at IS NULL OR ? > indexed_at THEN ?
                            ELSE indexed_at
                        END,
                        last_seen = CASE
                            WHEN ? > last_seen THEN ?
                            ELSE last_seen
                        END
                    WHERE url = ?
                    """,
                    (ts, ts, ts, ts, normalized),
                )
                self._conn.execute(
                    """
                    UPDATE domains
                    SET last_index_at = CASE
                            WHEN last_index_at IS NULL OR ? > last_index_at THEN ?
                            ELSE last_index_at
                        END
                    WHERE id = (
                        SELECT domain_id FROM pages WHERE url = ?
                    )
                    """,
                    (ts, ts, normalized),
                )


_DB_CACHE: dict[Path, LearnedWebDB] = {}
_DB_CACHE_LOCK = threading.Lock()


def _default_path() -> Path:
    data_dir = Path(os.getenv("DATA_DIR", "data"))
    return Path(os.getenv(_DEFAULT_DB_ENV, data_dir / "learned_web.sqlite3"))


def get_db(path: Optional[Path] = None) -> LearnedWebDB:
    resolved = Path(path) if path else _default_path()
    with _DB_CACHE_LOCK:
        db = _DB_CACHE.get(resolved)
        if db is None:
            db = LearnedWebDB(resolved)
            _DB_CACHE[resolved] = db
        return db
