"""High level helpers for the application state database."""

from __future__ import annotations

import json
import logging
import math
import threading
import time
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Mapping

from backend.app.services.source_follow import (
    SourceFollowConfig,
    SourceLink,
    normalize_config,
    serialize_config,
)

from .schema import connect, migrate


LOGGER = logging.getLogger(__name__)

SOURCES_CONFIG_KEY = "sources.config"


def _serialize(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


def _deserialize(payload: str | bytes | None, default: Any) -> Any:
    if not payload:
        return default
    try:
        return json.loads(payload)
    except (TypeError, json.JSONDecodeError):
        return default


def _ensure_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray)):
        return [str(item) for item in value]
    return []


def _parse_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


@dataclass(slots=True)
class DocumentRecord:
    id: str
    url: str
    canonical_url: str | None
    site: str | None
    title: str | None
    language: str | None
    fetched_at: float | None
    categories: list[str]
    labels: list[str]
    source: str | None
    normalized_path: str | None
    tokens: int | None


@dataclass(slots=True)
class SchemaValidation:
    """Schema validation snapshot used for diagnostics."""

    ok: bool
    tables: dict[str, dict[str, str]]
    errors: list[str]


class AppStateDB:
    """Thin wrapper around SQLite providing typed helpers."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = connect(path)
        migrate(self._conn)
        self._lock = threading.RLock()
        self._schema_validation: SchemaValidation = self._validate_schema()

    # ------------------------------------------------------------------
    # Tabs & history
    # ------------------------------------------------------------------
    def ensure_tab(self, tab_id: str, *, shadow_mode: str | None = None) -> None:
        if not tab_id:
            return
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR IGNORE INTO tabs(id) VALUES(?)",
                (tab_id,),
            )
            if shadow_mode:
                self._conn.execute(
                    "UPDATE tabs SET shadow_mode=? WHERE id=?",
                    (shadow_mode, tab_id),
                )

    def update_tab_shadow_mode(self, tab_id: str, mode: str | None) -> None:
        self.ensure_tab(tab_id)
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE tabs SET shadow_mode=? WHERE id=?",
                (mode, tab_id),
            )

    def tab_shadow_mode(self, tab_id: str) -> str | None:
        if not tab_id:
            return None
        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT shadow_mode FROM tabs WHERE id=?",
                (tab_id,),
            ).fetchone()
        if not row:
            return None
        value = row["shadow_mode"]
        return str(value) if value is not None else None

    def add_history_entry(
        self,
        *,
        tab_id: str | None,
        url: str,
        title: str | None = None,
        referrer: str | None = None,
        status_code: int | None = None,
        content_type: str | None = None,
        shadow_enqueued: bool = False,
    ) -> int:
        self.ensure_tab(tab_id or "")
        with self._lock, self._conn:
            cursor = self._conn.execute(
                """
                INSERT INTO history(tab_id, url, title, referrer, status_code, content_type, shadow_enqueued)
                VALUES(?,?,?,?,?,?,?)
                """,
                (tab_id, url, title, referrer, status_code, content_type, int(bool(shadow_enqueued))),
            )
            history_id = cursor.lastrowid
        return int(history_id)

    def mark_history_shadow_enqueued(self, history_id: int) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE history SET shadow_enqueued=1 WHERE id=?",
                (history_id,),
            )

    def delete_history_entry(self, history_id: int) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM history WHERE id=?", (history_id,))

    def query_history(
        self,
        *,
        limit: int = 200,
        query: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[dict[str, Any]]:
        sql = [
            "SELECT id, tab_id, url, title, visited_at, referrer, status_code, content_type, shadow_enqueued",
            "FROM history",
        ]
        clauses: list[str] = []
        params: list[Any] = []
        if query:
            pattern = f"%{query.lower()}%"
            clauses.append("(lower(url) LIKE ? OR lower(COALESCE(title,'')) LIKE ?)")
            params.extend([pattern, pattern])
        if start:
            clauses.append("visited_at >= ?")
            params.append(start.isoformat())
        if end:
            clauses.append("visited_at <= ?")
            params.append(end.isoformat())
        if clauses:
            sql.append("WHERE " + " AND ".join(clauses))
        sql.append("ORDER BY visited_at DESC")
        sql.append("LIMIT ?")
        params.append(max(1, min(int(limit), 1000)))
        query_sql = " ".join(sql)
        with self._lock, self._conn:
            rows = self._conn.execute(query_sql, params).fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # Bookmarks
    # ------------------------------------------------------------------
    @staticmethod
    def _encode_tags(tags: Iterable[str] | None) -> str | None:
        if not tags:
            return None
        normalized = sorted({str(tag).strip() for tag in tags if str(tag).strip()})
        if not normalized:
            return None
        return json.dumps(normalized, ensure_ascii=False)

    @staticmethod
    def _decode_tags(raw: str | None) -> list[str]:
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return [token.strip() for token in raw.split(",") if token.strip()]
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
        return []

    def create_bookmark_folder(self, name: str, parent_id: int | None = None) -> int:
        with self._lock, self._conn:
            cursor = self._conn.execute(
                "INSERT INTO bookmark_folders(name, parent_id) VALUES(?, ?)",
                (name, parent_id),
            )
            folder_id = cursor.lastrowid
        return int(folder_id)

    def list_bookmark_folders(self) -> list[dict[str, Any]]:
        with self._lock, self._conn:
            rows = self._conn.execute(
                "SELECT id, name, parent_id, created_at FROM bookmark_folders ORDER BY name ASC"
            ).fetchall()
        return [dict(row) for row in rows]

    def add_bookmark(
        self,
        *,
        url: str,
        title: str | None = None,
        folder_id: int | None = None,
        tags: Iterable[str] | None = None,
    ) -> int:
        payload_tags = self._encode_tags(tags)
        with self._lock, self._conn:
            cursor = self._conn.execute(
                "INSERT INTO bookmarks(folder_id, url, title, tags) VALUES(?,?,?,?)",
                (folder_id, url, title, payload_tags),
            )
            bookmark_id = cursor.lastrowid
        return int(bookmark_id)

    def list_bookmarks(self, folder_id: int | None = None) -> list[dict[str, Any]]:
        sql = "SELECT id, folder_id, url, title, tags, created_at FROM bookmarks"
        params: list[Any] = []
        if folder_id is not None:
            sql += " WHERE folder_id = ?"
            params.append(folder_id)
        sql += " ORDER BY created_at DESC"
        with self._lock, self._conn:
            rows = self._conn.execute(sql, params).fetchall()
        results = []
        for row in rows:
            record = dict(row)
            record["tags"] = self._decode_tags(row["tags"])
            results.append(record)
        return results

    # ------------------------------------------------------------------
    # Seed sources
    # ------------------------------------------------------------------
    def list_source_categories(self) -> list[dict[str, Any]]:
        with self._lock, self._conn:
            rows = self._conn.execute(
                "SELECT key, label FROM source_categories ORDER BY label ASC"
            ).fetchall()
        return [dict(row) for row in rows]

    def list_seed_sources(self) -> list[dict[str, Any]]:
        with self._lock, self._conn:
            rows = self._conn.execute(
                """
                SELECT id, category_key, url, title, added_by, enabled, created_at
                  FROM seed_sources
                 ORDER BY category_key ASC, created_at DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def bulk_upsert_seed_sources(self, seeds: Sequence[Mapping[str, Any]]) -> int:
        if not seeds:
            return 0
        with self._lock, self._conn:
            for seed in seeds:
                params = {
                    "category_key": seed.get("category_key"),
                    "url": seed.get("url"),
                    "title": seed.get("title"),
                    "added_by": seed.get("added_by", "user"),
                    "enabled": 1 if seed.get("enabled", True) else 0,
                }
                self._conn.execute(
                    """
                    INSERT INTO seed_sources(category_key, url, title, added_by, enabled)
                    VALUES(:category_key, :url, :title, :added_by, :enabled)
                    ON CONFLICT(category_key, url) DO UPDATE SET
                        title = COALESCE(excluded.title, seed_sources.title),
                        added_by = excluded.added_by,
                        enabled = excluded.enabled
                    """,
                    params,
                )
        return len(seeds)

    def enabled_seed_urls(self, category_keys: Sequence[str] | None = None) -> list[str]:
        sql = "SELECT url FROM seed_sources WHERE enabled = 1"
        params: list[Any] = []
        if category_keys:
            placeholders = ",".join("?" for _ in category_keys)
            sql += f" AND category_key IN ({placeholders})"
            params.extend(category_keys)
        sql += " ORDER BY created_at DESC"
        with self._lock, self._conn:
            rows = self._conn.execute(sql, params).fetchall()
        return [row["url"] for row in rows]

    # ------------------------------------------------------------------
    # Shadow settings & crawl queue
    # ------------------------------------------------------------------
    def get_shadow_settings(self) -> dict[str, Any]:
        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT enabled, mode FROM shadow_settings WHERE id=1"
            ).fetchone()
        if not row:
            return {"enabled": False, "mode": "off"}
        return {"enabled": bool(row["enabled"]), "mode": row["mode"] or "off"}

    def set_shadow_settings(self, *, enabled: bool, mode: str) -> dict[str, Any]:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO shadow_settings(id, enabled, mode)
                VALUES(1, ?, ?)
                ON CONFLICT(id) DO UPDATE SET enabled=excluded.enabled, mode=excluded.mode, updated_at=CURRENT_TIMESTAMP
                """,
                (int(bool(enabled)), mode),
            )
        return {"enabled": bool(enabled), "mode": mode}

    def effective_shadow_mode(self, tab_id: str | None) -> str:
        tab_mode = self.tab_shadow_mode(tab_id or "")
        if tab_mode and tab_mode != "off":
            return tab_mode
        settings = self.get_shadow_settings()
        if not settings.get("enabled"):
            return "off"
        return str(settings.get("mode") or "off")

    def enqueue_crawl_job(
        self,
        url: str,
        *,
        priority: int = 0,
        reason: str | None = None,
        parent_url: str | None = None,
        is_source: bool = False,
    ) -> str:
        job_id = uuid.uuid4().hex
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO crawl_jobs(
                    id,
                    status,
                    seed,
                    query,
                    normalized_path,
                    priority,
                    reason,
                    enqueued_at,
                    parent_url,
                    is_source
                )
                VALUES(?, 'queued', NULL, NULL, NULL, ?, ?, CURRENT_TIMESTAMP, ?, ?)
                """,
                (job_id, priority, reason, parent_url, int(bool(is_source))),
            )
            self._conn.execute(
                "INSERT INTO crawl_events(job_id, stage, payload) VALUES(?, ?, ?)",
                (
                    job_id,
                    "enqueue",
                    _serialize(
                        {
                            "url": url,
                            "reason": reason,
                            "priority": priority,
                            "parent_url": parent_url,
                            "is_source": bool(is_source),
                        }
                    ),
                ),
            )
        return job_id

    def crawl_overview(self) -> dict[str, int]:
        with self._lock, self._conn:
            rows = self._conn.execute(
                "SELECT status, COUNT(*) as total FROM crawl_jobs GROUP BY status"
            ).fetchall()
        summary = {"queued": 0, "running": 0, "done": 0, "error": 0}
        for row in rows:
            status = row["status"]
            if status == "success":
                summary["done"] += int(row["total"])
            elif status in summary:
                summary[status] += int(row["total"])
        return summary

    def crawl_job_status(self, job_id: str) -> dict[str, Any] | None:
        with self._lock, self._conn:
            row = self._conn.execute(
                """
                SELECT
                    id,
                    status,
                    seed,
                    query,
                    priority,
                    reason,
                    enqueued_at,
                    started_at,
                    finished_at,
                    error,
                    parent_url,
                    is_source
                  FROM crawl_jobs
                 WHERE id = ?
                """,
                (job_id,),
            ).fetchone()
        if not row:
            return None
        return dict(row)

    def enqueue_seed_jobs(self, category_keys: Sequence[str], *, priority: int = 0) -> list[str]:
        urls = self.enabled_seed_urls(category_keys)
        job_ids: list[str] = []
        for url in urls:
            job_ids.append(self.enqueue_crawl_job(url, priority=priority, reason="seed"))
        return job_ids

    # ------------------------------------------------------------------
    # Graph queries
    # ------------------------------------------------------------------
    def graph_summary(self) -> dict[str, Any]:
        seven_days_ago = datetime.utcnow() - timedelta(days=7)
        with self._lock, self._conn:
            page_total = self._conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
            site_total = self._conn.execute(
                "SELECT COUNT(DISTINCT site) FROM pages WHERE site IS NOT NULL"
            ).fetchone()[0]
            fresh = self._conn.execute(
                "SELECT COUNT(*) FROM pages WHERE last_seen IS NOT NULL AND last_seen >= ?",
                (seven_days_ago.isoformat(),),
            ).fetchone()[0]
            top_sites = self._conn.execute(
                """
                SELECT site, COUNT(*) as degree
                  FROM link_edges
                  JOIN pages ON pages.url = link_edges.dst_url
                 WHERE site IS NOT NULL
              GROUP BY site
              ORDER BY degree DESC
              LIMIT 5
                """
            ).fetchall()
        clusters = []
        for row in top_sites:
            clusters.append({"site": row["site"], "degree": row["degree"]})
        return {
            "pages": int(page_total),
            "sites": int(site_total),
            "fresh_7d": int(fresh),
            "top_sites": clusters,
        }

    def graph_nodes(
        self,
        *,
        site: str | None = None,
        limit: int = 200,
        min_degree: int = 0,
        category: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[dict[str, Any]]:
        sql = [
            "SELECT id, url, site, title, first_seen, last_seen, topics",
            "FROM pages",
        ]
        clauses: list[str] = []
        params: list[Any] = []
        if site:
            clauses.append("site = ?")
            params.append(site)
        if start:
            clauses.append("last_seen >= ?")
            params.append(start.isoformat())
        if end:
            clauses.append("last_seen <= ?")
            params.append(end.isoformat())
        if category:
            clauses.append("topics LIKE ?")
            params.append(f"%{category}%")
        if clauses:
            sql.append("WHERE " + " AND ".join(clauses))
        sql.append("ORDER BY last_seen DESC")
        sql.append("LIMIT ?")
        params.append(max(1, min(limit, 1000)))
        query_sql = " ".join(sql)
        with self._lock, self._conn:
            rows = self._conn.execute(query_sql, params).fetchall()
        results: list[dict[str, Any]] = []
        for row in rows:
            record = dict(row)
            record["topics"] = self._decode_tags(row["topics"])
            if min_degree > 0:
                degree = self._page_degree(row["url"])
                if degree < min_degree:
                    continue
                record["degree"] = degree
            results.append(record)
        return results

    def _page_degree(self, url: str) -> int:
        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT COUNT(*) FROM link_edges WHERE src_url = ? OR dst_url = ?",
                (url, url),
            ).fetchone()
        return int(row[0]) if row else 0

    def graph_edges(
        self,
        *,
        site: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        sql = [
            "SELECT src_url, dst_url, relation",
            "FROM link_edges",
        ]
        params: list[Any] = []
        if site:
            sql.append(
                "WHERE src_url IN (SELECT url FROM pages WHERE site = ?) OR dst_url IN (SELECT url FROM pages WHERE site = ?)"
            )
            params.extend([site, site])
        sql.append("LIMIT ?")
        params.append(max(1, min(limit, 2000)))
        query_sql = " ".join(sql)
        with self._lock, self._conn:
            rows = self._conn.execute(query_sql, params).fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # Crawl jobs
    # ------------------------------------------------------------------
    def record_crawl_job(
        self,
        job_id: str,
        *,
        seed: str | None = None,
        query: str | None = None,
        normalized_path: str | None = None,
        parent_url: str | None = None,
        is_source: bool = False,
    ) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO crawl_jobs(id, status, seed, query, normalized_path, parent_url, is_source)
                VALUES(?, 'queued', ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    seed=excluded.seed,
                    query=excluded.query,
                    parent_url=COALESCE(excluded.parent_url, crawl_jobs.parent_url),
                    is_source=excluded.is_source
                """,
                (job_id, seed, query, normalized_path, parent_url, int(bool(is_source))),
            )
    def pending_crawl_jobs(self) -> list[dict[str, Any]]:
        with self._lock, self._conn:
            rows = self._conn.execute(
                "SELECT id, query, seed, status FROM crawl_jobs WHERE status IN ('queued','running')"
            ).fetchall()
        return [dict(row) for row in rows]



    def update_crawl_status(self, job_id: str, status: str, *, stats: Mapping[str, Any] | None = None,
                             error: str | None = None, preview: Iterable[Mapping[str, Any]] | None = None,
                             normalized_path: str | None = None) -> None:
        preview_payload = _serialize(list(preview)) if preview is not None else None
        stats_payload = _serialize(dict(stats)) if stats is not None else None
        with self._lock, self._conn:
            self._conn.execute(
                """
                UPDATE crawl_jobs
                   SET status = ?,
                       error = ?,
                       stats = COALESCE(?, stats),
                       normalized_path = COALESCE(?, normalized_path),
                       preview_json = COALESCE(?, preview_json)
                 WHERE id = ?
                """,
                (status, error, stats_payload, normalized_path, preview_payload, job_id),
            )

    def record_crawl_event(self, job_id: str, stage: str, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        event_payload = _serialize(payload or {})
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO crawl_events(job_id, stage, payload) VALUES(?, ?, ?)",
                (job_id, stage, event_payload),
            )
            stats = self._conn.execute(
                "SELECT stats FROM crawl_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
            current = _deserialize(stats["stats"] if stats else None, {})
            if stage == "fetch_ok":
                current["fetch_ok"] = int(current.get("fetch_ok", 0)) + 1
            elif stage == "fetch_err":
                current["fetch_err"] = int(current.get("fetch_err", 0)) + 1
            elif stage in {"index", "index_complete"}:
                added = int((payload or {}).get("added", 0))
                if added == 0:
                    added = int((payload or {}).get("docs_indexed", 0))
                current["indexed"] = int(current.get("indexed", 0)) + added
            elif stage in {"normalize", "normalize_complete"}:
                docs_count = int((payload or {}).get("docs", 0))
                current["normalized"] = int(current.get("normalized", 0)) + docs_count
            self._conn.execute(
                "UPDATE crawl_jobs SET stats = ? WHERE id = ?",
                (_serialize(current), job_id),
            )
        return current

    # ------------------------------------------------------------------
    # Documents
    # ------------------------------------------------------------------
    def upsert_document(
        self,
        *,
        job_id: str | None,
        document_id: str,
        url: str,
        canonical_url: str | None,
        site: str | None,
        title: str | None,
        description: str | None,
        language: str | None,
        fetched_at: float | None,
        normalized_path: str | None,
        text_len: int | None,
        tokens: int | None,
        content_hash: str | None,
        categories: Iterable[str] | None,
        labels: Iterable[str] | None,
        source: str | None,
        verification: Mapping[str, Any] | None = None,
    ) -> None:
        categories_json = _serialize(_ensure_list(categories or []))
        labels_json = _serialize(_ensure_list(labels or []))
        verification_json = _serialize(verification) if verification is not None else None
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO documents(
                    id, url, canonical_url, site, title, description, language, fetched_at,
                    normalized_path, text_len, tokens, content_hash, categories, labels,
                    source, last_seen, job_id, verification
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    url = excluded.url,
                    canonical_url = excluded.canonical_url,
                    site = excluded.site,
                    title = excluded.title,
                    description = excluded.description,
                    language = excluded.language,
                    fetched_at = excluded.fetched_at,
                    normalized_path = excluded.normalized_path,
                    text_len = excluded.text_len,
                    tokens = excluded.tokens,
                    content_hash = excluded.content_hash,
                    categories = excluded.categories,
                    labels = CASE WHEN excluded.labels != '[]' THEN excluded.labels ELSE documents.labels END,
                    source = excluded.source,
                    last_seen = CURRENT_TIMESTAMP,
                    job_id = excluded.job_id,
                    verification = excluded.verification
                """,
                (
                    document_id,
                    url,
                    canonical_url,
                    site,
                    title,
                    description,
                    language,
                    fetched_at,
                    normalized_path,
                    text_len,
                    tokens,
                    content_hash,
                    categories_json,
                    labels_json,
                    source,
                    job_id,
                    verification_json,
                ),
            )

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------
    def schema_diagnostics(self, *, refresh: bool = False) -> dict[str, Any]:
        """Return the schema validation snapshot used for diagnostics."""

        if refresh or self._schema_validation is None:
            self._schema_validation = self._validate_schema()
        snapshot = self._schema_validation
        return {
            "ok": snapshot.ok,
            "tables": {table: dict(columns) for table, columns in snapshot.tables.items()},
            "errors": list(snapshot.errors),
        }

    def _validate_schema(self) -> SchemaValidation:
        expected: dict[str, dict[str, str]] = {
            "pending_documents": {
                "job_id": "TEXT",
                "doc_hash": "TEXT",
                "sim_signature": "TEXT",
                "created_at": "INTEGER",
                "updated_at": "INTEGER",
            },
            "pending_chunks": {
                "created_at": "INTEGER",
                "updated_at": "INTEGER",
            },
            "pending_vectors_queue": {
                "created_at": "INTEGER",
                "updated_at": "INTEGER",
                "next_attempt_at": "INTEGER",
            },
        }
        tables: dict[str, dict[str, str]] = {}
        errors: list[str] = []
        ok = True

        for table, columns in expected.items():
            info = self._conn.execute(f"PRAGMA table_info('{table}')").fetchall()
            table_columns: dict[str, str] = {}
            for row in info:
                name = row["name"] if isinstance(row, Mapping) else row[1]
                declared = row["type"] if isinstance(row, Mapping) else row[2]
                table_columns[str(name)] = str(declared or "").upper()
            tables[table] = table_columns
            for column, expected_type in columns.items():
                actual = table_columns.get(column, "")
                if actual != expected_type:
                    ok = False
                    errors.append(
                        f"{table}.{column} expected {expected_type} got {actual or 'missing'}"
                    )

        if not ok:
            LOGGER.error(
                "app state schema validation failed: %s",
                "; ".join(errors) if errors else "unknown mismatch",
            )

        return SchemaValidation(ok=ok, tables=tables, errors=errors)

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------
    def get_setting(self, key: str, default: str | None = None) -> str | None:
        with self._lock, self._conn:
            cursor = self._conn.execute(
                "SELECT value FROM app_settings WHERE key = ?",
                (key,),
            )
            row = cursor.fetchone()
        if row is None:
            return default
        value = row["value"] if isinstance(row, Mapping) else row[0]
        return str(value)

    def set_setting(self, key: str, value: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO app_settings(key, value, updated_at)
                VALUES(?, ?, strftime('%s','now'))
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (key, value),
            )

    def get_sources_config(self) -> SourceFollowConfig:
        raw = self.get_setting(SOURCES_CONFIG_KEY)
        payload: Mapping[str, object] | None = None
        if raw:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, Mapping):
                    payload = parsed
            except json.JSONDecodeError:
                LOGGER.warning("invalid sources config JSON; using defaults")
        return normalize_config(payload)

    def set_sources_config(
        self, config: SourceFollowConfig | Mapping[str, object]
    ) -> SourceFollowConfig:
        if isinstance(config, SourceFollowConfig):
            normalized = config
        else:
            normalized = normalize_config(config)
        serialized = serialize_config(normalized)
        self.set_setting(SOURCES_CONFIG_KEY, serialized)
        return normalized

    # ------------------------------------------------------------------
    # Source discovery records
    # ------------------------------------------------------------------
    def record_source_links(
        self,
        parent_url: str,
        links: Sequence[SourceLink],
        *,
        mark_enqueued: bool = False,
    ) -> None:
        if not parent_url or not links:
            return
        enqueued_flag = 1 if mark_enqueued else 0
        with self._lock, self._conn:
            for link in links:
                self._conn.execute(
                    """
                    INSERT INTO source_links(parent_url, source_url, kind, enqueued)
                    VALUES(?, ?, ?, ?)
                    ON CONFLICT(parent_url, source_url) DO UPDATE SET
                        kind = excluded.kind,
                        enqueued = CASE
                            WHEN source_links.enqueued = 1 THEN 1
                            ELSE excluded.enqueued
                        END
                    """,
                    (parent_url, link.url, link.kind, enqueued_flag),
                )

    def mark_sources_enqueued(self, parent_url: str, urls: Sequence[str]) -> None:
        if not parent_url or not urls:
            return
        with self._lock, self._conn:
            for url in urls:
                self._conn.execute(
                    "UPDATE source_links SET enqueued = 1 WHERE parent_url = ? AND source_url = ?",
                    (parent_url, url),
                )

    def record_missing_source(
        self,
        parent_url: str,
        source_url: str,
        *,
        reason: str,
        http_status: int | None = None,
        next_action: str | None = None,
        notes: str | None = None,
    ) -> None:
        if not parent_url or not source_url:
            return
        timestamp = int(time.time())
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO missing_sources(parent_url, source_url, reason, http_status, last_attempt, retries, next_action, notes)
                VALUES(?, ?, ?, ?, ?, 0, ?, ?)
                ON CONFLICT(parent_url, source_url) DO UPDATE SET
                    reason = excluded.reason,
                    http_status = excluded.http_status,
                    last_attempt = excluded.last_attempt,
                    retries = missing_sources.retries + 1,
                    next_action = COALESCE(excluded.next_action, missing_sources.next_action),
                    notes = COALESCE(excluded.notes, missing_sources.notes)
                """,
                (
                    parent_url,
                    source_url,
                    reason,
                    http_status,
                    timestamp,
                    next_action,
                    notes,
                ),
            )

    def resolve_missing_source(self, parent_url: str, source_url: str, *, notes: str | None = None) -> None:
        if not parent_url or not source_url:
            return
        with self._lock, self._conn:
            self._conn.execute(
                "DELETE FROM missing_sources WHERE parent_url = ? AND source_url = ?",
                (parent_url, source_url),
            )
            if notes:
                self._conn.execute(
                    """
                    INSERT INTO source_links(parent_url, source_url, kind, enqueued, discovered_at)
                    VALUES(?, ?, 'resolved', 1, CURRENT_TIMESTAMP)
                    ON CONFLICT(parent_url, source_url) DO UPDATE SET
                        enqueued = 1
                    """,
                    (parent_url, source_url),
                )

    def list_missing_sources(
        self,
        *,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        capped = max(1, min(int(limit), 500))
        with self._lock, self._conn:
            rows = self._conn.execute(
                """
                SELECT id, parent_url, source_url, reason, http_status, last_attempt, retries, next_action, notes
                FROM missing_sources
                ORDER BY COALESCE(last_attempt, 0) DESC
                LIMIT ?
                """,
                (capped,),
            ).fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # Pending vectors
    # ------------------------------------------------------------------
    def enqueue_pending_document(
        self,
        *,
        doc_id: str,
        job_id: str | None,
        url: str | None,
        title: str | None,
        resolved_title: str,
        doc_hash: str,
        sim_signature: int | None,
        metadata: Mapping[str, Any] | None,
        chunks: Sequence[tuple[int, str, Mapping[str, Any] | None]],
        initial_delay: float = 0.0,
        last_error: str | None = None,
    ) -> None:
        metadata_json = _serialize(metadata or {})
        job_id_str = str(job_id) if job_id is not None else None
        doc_hash_str = str(doc_hash or "")
        if not doc_hash_str:
            raise ValueError("doc_hash must be a non-empty string")
        sim_signature_str: str | None
        if sim_signature is None:
            sim_signature_str = None
        else:
            try:
                sim_signature_str = str(int(sim_signature))
            except (TypeError, ValueError):
                sim_signature_str = str(sim_signature)
        now = int(time.time())
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO pending_documents(
                    doc_id,
                    job_id,
                    url,
                    title,
                    resolved_title,
                    doc_hash,
                    sim_signature,
                    metadata,
                    last_error,
                    created_at,
                    updated_at
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(doc_id) DO UPDATE SET
                    job_id = excluded.job_id,
                    url = excluded.url,
                    title = excluded.title,
                    resolved_title = excluded.resolved_title,
                    doc_hash = excluded.doc_hash,
                    sim_signature = excluded.sim_signature,
                    metadata = excluded.metadata,
                    last_error = COALESCE(excluded.last_error, pending_documents.last_error),
                    retry_count = CASE
                        WHEN excluded.last_error IS NOT NULL THEN COALESCE(pending_documents.retry_count, 0)
                        ELSE pending_documents.retry_count
                    END,
                    updated_at = ?
                """,
                (
                    doc_id,
                    job_id_str,
                    url,
                    title,
                    resolved_title,
                    doc_hash_str,
                    sim_signature_str,
                    metadata_json,
                    last_error,
                    now,
                    now,
                    now,
                ),
            )
            self._conn.execute(
                "DELETE FROM pending_chunks WHERE doc_id = ?",
                (doc_id,),
            )
            for index, text, chunk_metadata in chunks:
                self._conn.execute(
                    """
                    INSERT INTO pending_chunks(doc_id, chunk_index, text, metadata, created_at, updated_at)
                    VALUES(?, ?, ?, ?, ?, ?)
                    ON CONFLICT(doc_id, chunk_index) DO UPDATE SET
                        text = excluded.text,
                        metadata = excluded.metadata,
                        updated_at = ?
                    """,
                    (
                        doc_id,
                        int(index),
                        text,
                        _serialize(chunk_metadata or {}),
                        now,
                        now,
                        now,
                    ),
                )
            next_attempt = max(
                int(math.ceil(now + max(0.0, float(initial_delay)))),
                now,
            )
            self._conn.execute(
                """
                INSERT INTO pending_vectors_queue(doc_id, attempts, next_attempt_at, created_at, updated_at)
                VALUES(?, 0, ?, ?, ?)
                ON CONFLICT(doc_id) DO UPDATE SET
                    next_attempt_at = ?,
                    updated_at = ?
                """,
                (doc_id, next_attempt, now, now, next_attempt, now),
            )

    def pop_pending_documents(self, limit: int = 5) -> list[dict[str, Any]]:
        now = int(time.time())
        rows: list[dict[str, Any]] = []
        with self._lock, self._conn:
            cursor = self._conn.execute(
                """
                SELECT q.doc_id, q.attempts, d.job_id, d.url, d.title, d.resolved_title, d.doc_hash,
                       d.sim_signature, d.metadata, d.last_error, d.retry_count
                  FROM pending_vectors_queue AS q
                  JOIN pending_documents AS d ON d.doc_id = q.doc_id
                 WHERE q.next_attempt_at <= ?
                 ORDER BY q.next_attempt_at ASC
                 LIMIT ?
                """,
                (now, int(limit)),
            )
            candidates = list(cursor.fetchall())
            for row in candidates:
                doc_id = row["doc_id"]
                chunk_rows = self._conn.execute(
                    "SELECT chunk_index, text, metadata FROM pending_chunks WHERE doc_id = ? ORDER BY chunk_index ASC",
                    (doc_id,),
                ).fetchall()
                chunks = [
                    {
                        "index": chunk_row["chunk_index"],
                        "text": chunk_row["text"],
                        "metadata": _deserialize(chunk_row["metadata"], {}),
                    }
                    for chunk_row in chunk_rows
                ]
                rows.append(
                    {
                        "doc_id": doc_id,
                        "attempts": _parse_int(row["attempts"]) or 0,
                        "job_id": row["job_id"],
                        "url": row["url"],
                        "title": row["title"],
                        "resolved_title": row["resolved_title"],
                        "doc_hash": row["doc_hash"],
                        "sim_signature": _parse_int(row["sim_signature"]),
                        "metadata": _deserialize(row["metadata"], {}),
                        "chunks": chunks,
                        "last_error": row["last_error"],
                        "retry_count": _parse_int(row["retry_count"]) or 0,
                    }
                )
                self._conn.execute(
                    "DELETE FROM pending_vectors_queue WHERE doc_id = ?",
                    (doc_id,),
                )
        return rows

    def reschedule_pending_document(
        self,
        doc_id: str,
        *,
        delay: float,
        attempts: int,
        last_error: str | None = None,
    ) -> None:
        now = int(time.time())
        next_attempt = int(
            math.ceil(now + max(1.0, float(delay)))
        )
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO pending_vectors_queue(doc_id, attempts, next_attempt_at, created_at, updated_at)
                VALUES(?, ?, ?, ?, ?)
                ON CONFLICT(doc_id) DO UPDATE SET
                    attempts = ?,
                    next_attempt_at = ?,
                    updated_at = ?
                """,
                (
                    doc_id,
                    int(attempts),
                    next_attempt,
                    now,
                    now,
                    int(attempts),
                    next_attempt,
                    now,
                ),
            )
            self._conn.execute(
                """
                UPDATE pending_documents
                   SET retry_count = ?,
                       last_error = COALESCE(?, last_error),
                       updated_at = ?
                 WHERE doc_id = ?
                """,
                (int(attempts), last_error, now, doc_id),
            )

    def clear_pending_document(self, doc_id: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM pending_documents WHERE doc_id = ?", (doc_id,))

    def list_pending_documents(self, limit: int = 200) -> list[dict[str, Any]]:
        with self._lock, self._conn:
            cursor = self._conn.execute(
                """
                SELECT doc_id, url, title, retry_count, last_error, updated_at
                  FROM pending_documents
              ORDER BY updated_at DESC
                 LIMIT ?
                """,
                (int(limit),),
            )
            rows = cursor.fetchall()
        results: list[dict[str, Any]] = []
        for row in rows:
            if isinstance(row, Mapping):
                results.append(
                    {
                        "doc_id": row.get("doc_id"),
                        "url": row.get("url"),
                        "title": row.get("title"),
                        "retry_count": row.get("retry_count"),
                        "last_error": row.get("last_error"),
                        "updated_at": row.get("updated_at"),
                    }
                )
            else:
                results.append(
                    {
                        "doc_id": row[0],
                        "url": row[1],
                        "title": row[2],
                        "retry_count": row[3],
                        "last_error": row[4],
                        "updated_at": row[5],
                    }
                )
        return results

    # ------------------------------------------------------------------
    # Job status
    # ------------------------------------------------------------------
    def upsert_job_status(
        self,
        job_id: str,
        *,
        url: str | None,
        phase: str,
        steps_total: int,
        steps_completed: int,
        retries: int,
        eta_seconds: float | None,
        message: str | None,
        started_at: float | None = None,
    ) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO job_status(
                    job_id, url, phase, steps_total, steps_completed, retries, eta_seconds, message, started_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, COALESCE(?, strftime('%s','now')), strftime('%s','now'))
                ON CONFLICT(job_id) DO UPDATE SET
                    url = COALESCE(excluded.url, job_status.url),
                    phase = excluded.phase,
                    steps_total = excluded.steps_total,
                    steps_completed = excluded.steps_completed,
                    retries = excluded.retries,
                    eta_seconds = excluded.eta_seconds,
                    message = excluded.message,
                    started_at = COALESCE(job_status.started_at, excluded.started_at),
                    updated_at = excluded.updated_at
                """,
                (
                    job_id,
                    url,
                    phase,
                    int(steps_total),
                    int(steps_completed),
                    int(retries),
                    eta_seconds,
                    message,
                    started_at,
                ),
            )

    def get_job_status(self, job_id: str) -> dict[str, Any] | None:
        with self._lock, self._conn:
            cursor = self._conn.execute(
                """
                SELECT job_id, url, phase, steps_total, steps_completed, retries, eta_seconds, message, started_at, updated_at
                  FROM job_status
                 WHERE job_id = ?
                """,
                (job_id,),
            )
            row = cursor.fetchone()
        if not row:
            return None
        if isinstance(row, Mapping):
            return dict(row)
        keys = [
            "job_id",
            "url",
            "phase",
            "steps_total",
            "steps_completed",
            "retries",
            "eta_seconds",
            "message",
            "started_at",
            "updated_at",
        ]
        return {key: row[index] for index, key in enumerate(keys)}

    def list_documents(self, *, query: str | None = None, site: str | None = None, limit: int = 100) -> list[DocumentRecord]:
        conditions: list[str] = []
        params: list[Any] = []
        if query:
            like = f"%{query.strip()}%"
            conditions.append("(url LIKE ? OR title LIKE ?)")
            params.extend([like, like])
        if site:
            conditions.append("site = ?")
            params.append(site)
        sql = """
            SELECT id, url, canonical_url, site, title, language, fetched_at,
                   categories, labels, source, normalized_path, tokens
              FROM documents
        """
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY last_seen DESC LIMIT ?"
        params.append(limit)
        rows = self._conn.execute(sql, params).fetchall()
        results: list[DocumentRecord] = []
        for row in rows:
            results.append(
                DocumentRecord(
                    id=row["id"],
                    url=row["url"],
                    canonical_url=row["canonical_url"],
                    site=row["site"],
                    title=row["title"],
                    language=row["language"],
                    fetched_at=row["fetched_at"],
                    categories=_ensure_list(_deserialize(row["categories"], [])),
                    labels=_ensure_list(_deserialize(row["labels"], [])),
                    source=row["source"],
                    normalized_path=row["normalized_path"],
                    tokens=row["tokens"],
                )
            )
        return results

    def get_document(self, document_id: str) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        if not row:
            return None
        payload = dict(row)
        payload["categories"] = _ensure_list(_deserialize(payload.get("categories"), []))
        payload["labels"] = _ensure_list(_deserialize(payload.get("labels"), []))
        payload["verification"] = _deserialize(payload.get("verification"), {})
        return payload

    def fetch_documents_for_labeling(self, *, limit: int = 5) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT id, url, title, description, language
              FROM documents
             WHERE (labels IS NULL OR labels = '[]')
          ORDER BY last_seen DESC
             LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    def update_document_labels(self, document_id: str, labels: Iterable[str]) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE documents SET labels = ?, last_seen = CURRENT_TIMESTAMP WHERE id = ?",
                (_serialize(_ensure_list(labels)), document_id),
            )

    # ------------------------------------------------------------------
    # Visits
    # ------------------------------------------------------------------
    def record_visit(self, url: str, *, referer: str | None, dur_ms: int | None, source: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO page_visits(url, referer, dur_ms, source) VALUES(?, ?, ?, ?)",
                (url, referer, dur_ms, source),
            )

    # ------------------------------------------------------------------
    # Chat history
    # ------------------------------------------------------------------
    def upsert_thread(self, thread_id: str, *, title: str | None = None) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO chat_threads(id, title, last_activity)
                VALUES(?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET last_activity = CURRENT_TIMESTAMP,
                                           title = COALESCE(excluded.title, chat_threads.title)
                """,
                (thread_id, title),
            )

    def add_chat_message(self, *, message_id: str | None, thread_id: str, role: str, content: str,
                          tokens: int | None = None) -> str:
        msg_id = message_id or uuid.uuid4().hex
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO chat_messages(id, thread_id, role, content, tokens)
                VALUES(?, ?, ?, ?, ?)
                """,
                (msg_id, thread_id, role, content, tokens),
            )
            self._conn.execute(
                "UPDATE chat_threads SET last_activity = CURRENT_TIMESTAMP WHERE id = ?",
                (thread_id,),
            )
        return msg_id

    def recent_messages(self, thread_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT role, content, created_at, tokens
              FROM chat_messages
             WHERE thread_id = ?
          ORDER BY created_at DESC
             LIMIT ?
            """,
            (thread_id, limit),
        ).fetchall()
        return [dict(row) for row in rows][::-1]

    def get_summary(self, thread_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT summary, updated_at, embedding_ref FROM chat_summaries WHERE thread_id = ?",
            (thread_id,),
        ).fetchone()
        return dict(row) if row else None

    def upsert_summary(self, thread_id: str, *, summary: str, embedding_ref: str | None = None) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO chat_summaries(thread_id, summary, embedding_ref)
                VALUES(?, ?, ?)
                ON CONFLICT(thread_id) DO UPDATE SET summary = excluded.summary,
                                                    embedding_ref = COALESCE(excluded.embedding_ref, chat_summaries.embedding_ref),
                                                    updated_at = CURRENT_TIMESTAMP
                """,
                (thread_id, summary, embedding_ref),
            )

    # ------------------------------------------------------------------
    # Memories
    # ------------------------------------------------------------------
    def upsert_memory(
        self,
        *,
        memory_id: str,
        scope: str,
        scope_ref: str | None,
        key: str | None,
        value: str,
        metadata: Mapping[str, Any] | None,
        strength: float,
    ) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO memories(id, scope, scope_ref, key, value, metadata, strength)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    scope = excluded.scope,
                    scope_ref = excluded.scope_ref,
                    key = excluded.key,
                    value = excluded.value,
                    metadata = excluded.metadata,
                    strength = excluded.strength,
                    last_accessed = CURRENT_TIMESTAMP
                """,
                (memory_id, scope, scope_ref, key, value, _serialize(metadata or {}), strength),
            )
            self._conn.execute(
                "INSERT INTO memory_audit(memory_id, action, detail) VALUES(?, 'upsert', ?)",
                (memory_id, value[:2000]),
            )

    def list_memories(self, *, scope: str, scope_ref: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT id, scope, scope_ref, key, value, metadata, strength, last_accessed, created_at
              FROM memories
             WHERE scope = ? AND (scope_ref = ? OR ? IS NULL)
          ORDER BY last_accessed DESC
             LIMIT ?
            """,
            (scope, scope_ref, scope_ref, limit),
        ).fetchall()
        items: list[dict[str, Any]] = []
        for row in rows:
            payload = dict(row)
            payload["metadata"] = _deserialize(payload.get("metadata"), {})
            items.append(payload)
        return items

    def age_memories(self, *, decay: float = 0.9, floor: float = 0.05) -> None:
        with self._lock, self._conn:
            rows = self._conn.execute(
                "SELECT id, strength FROM memories",
            ).fetchall()
            for row in rows:
                current = float(row["strength"] or 0.0)
                aged = max(floor, current * decay)
                self._conn.execute(
                    "UPDATE memories SET strength = ?, last_accessed = CURRENT_TIMESTAMP WHERE id = ?",
                    (aged, row["id"]),
                )
                self._conn.execute(
                    "INSERT INTO memory_audit(memory_id, action, detail) VALUES(?, 'age', ?)",
                    (row["id"], f"{current:.3f}->{aged:.3f}"),
                )

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------
    def close(self) -> None:
        with self._lock:
            self._conn.close()
