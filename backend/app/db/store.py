"""High level helpers for the application state database."""

from __future__ import annotations

import json
import logging
import math
import sqlite3
import threading
import time
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

from backend.app.services.source_follow import (
    SourceFollowConfig,
    SourceLink,
    normalize_config,
    serialize_config,
)

from .schema import connect, migrate


LOGGER = logging.getLogger(__name__)

SOURCES_CONFIG_KEY = "sources.config"
JOB_STATUSES = {"queued", "running", "succeeded", "failed", "cancelled"}


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


def _normalize_repo_ops(ops: Any) -> list[str]:
    normalized: list[str] = []
    for entry in _ensure_list(ops):
        candidate = entry.strip().lower()
        if not candidate:
            continue
        if candidate not in normalized:
            normalized.append(candidate)
    return normalized


def _normalize_command(command: Any) -> list[str] | None:
    if command is None:
        return None
    if isinstance(command, str):
        candidate = command.strip()
        return [candidate] if candidate else None
    if isinstance(command, Iterable) and not isinstance(command, (bytes, bytearray)):
        entries: list[str] = []
        for item in command:
            if item is None:
                continue
            text = str(item).strip()
            if not text:
                continue
            entries.append(text)
        return entries or None
    return None


def _parse_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _utc_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")


def _normalize_site(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = urlparse(value)
    except Exception:
        parsed = None
    host = parsed.hostname if parsed else None
    if not host:
        host = value
    host = host.strip().lower()
    return host or None


def _normalize_links(outlinks: Iterable[str] | None) -> list[str]:
    if not outlinks:
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in outlinks:
        if not isinstance(raw, str):
            continue
        text = raw.strip()
        if not text:
            continue
        try:
            parsed = urlparse(text)
        except Exception:
            continue
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            continue
        normalized_url = parsed.geturl()
        if normalized_url in seen:
            continue
        seen.add(normalized_url)
        normalized.append(normalized_url)
    return normalized


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
        LOGGER.info("Running state DB migrations", extra={"db_path": str(self.path)})
        migrate(self._conn)
        LOGGER.info("State DB migrations finished", extra={"db_path": str(self.path)})
        self._lock = threading.RLock()
        self._schema_validation: SchemaValidation = self._validate_schema()

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------
    def config_snapshot(self) -> dict[str, Any]:
        with self._lock, self._conn:
            rows = list(self._conn.execute("SELECT k, v FROM app_config"))
        snapshot: dict[str, Any] = {}
        for row in rows:
            key = str(row["k"]) if row["k"] is not None else ""
            if not key:
                continue
            snapshot[key] = _deserialize(row["v"], None)
        return snapshot

    def get_config(self, key: str, default: Any = None) -> Any:
        if not key:
            return default
        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT v FROM app_config WHERE k=?",
                (key,),
            ).fetchone()
        payload = row["v"] if row is not None else None
        return _deserialize(payload, default)

    def set_config(self, key: str, value: Any) -> None:
        if not key:
            raise ValueError("config key required")
        serialized = _serialize(value)
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO app_config(k, v) VALUES(?, ?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
                (key, serialized),
            )

    def update_config(self, values: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(values, Mapping):
            raise TypeError("values must be a mapping")
        with self._lock, self._conn:
            for key, value in values.items():
                normalized_key = str(key or "").strip()
                if not normalized_key:
                    continue
                serialized = _serialize(value)
                self._conn.execute(
                    "INSERT INTO app_config(k, v) VALUES(?, ?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
                    (normalized_key, serialized),
                )
        return self.config_snapshot()

    # ------------------------------------------------------------------
    # Repository registry
    # ------------------------------------------------------------------
    def register_repo(
        self,
        repo_id: str,
        *,
        root_path: Path | str,
        allowed_ops: Iterable[str] | None = None,
        check_command: Iterable[str] | str | None = None,
    ) -> dict[str, Any]:
        if not repo_id:
            raise ValueError("repo_id is required")
        normalized_ops = _normalize_repo_ops(allowed_ops) or ["read"]
        payload = _serialize(normalized_ops)
        normalized_command = _normalize_command(check_command)
        command_payload = _serialize(normalized_command) if normalized_command else None
        resolved_root = str(Path(root_path).resolve())
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO repos(id, root_path, allowed_ops, check_command, created_at, updated_at)
                VALUES(?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    root_path = excluded.root_path,
                    allowed_ops = excluded.allowed_ops,
                    check_command = COALESCE(excluded.check_command, repos.check_command),
                    updated_at = CURRENT_TIMESTAMP
                """,
                (repo_id, resolved_root, payload, command_payload),
            )
        record = self.get_repo(repo_id)
        if record is None:
            raise RuntimeError(f"failed to register repo {repo_id}")
        return record

    def get_repo(self, repo_id: str) -> dict[str, Any] | None:
        if not repo_id:
            return None
        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT id, root_path, allowed_ops, check_command, created_at, updated_at FROM repos WHERE id = ?",
                (repo_id,),
            ).fetchone()
        if not row:
            return None
        return self._format_repo_row(row)

    def list_repos(self) -> list[dict[str, Any]]:
        with self._lock, self._conn:
            rows = self._conn.execute(
                "SELECT id, root_path, allowed_ops, check_command, created_at, updated_at FROM repos ORDER BY id ASC"
            ).fetchall()
        return [self._format_repo_row(row) for row in rows]

    def _format_repo_row(self, row: Mapping[str, Any] | sqlite3.Row) -> dict[str, Any]:
        payload = dict(row)
        payload["allowed_ops"] = _normalize_repo_ops(
            _deserialize(payload.get("allowed_ops"), [])
        )
        payload["check_command"] = _normalize_command(
            _deserialize(payload.get("check_command"), None)
        )
        return payload

    def record_repo_change(
        self,
        repo_id: str,
        *,
        summary: str,
        change_stats: Mapping[str, Any] | None,
        result: str,
        error_message: str | None = None,
        job_id: str | None = None,
    ) -> str:
        if not repo_id:
            raise ValueError("repo_id is required")
        identifier = uuid.uuid4().hex
        stats_json = _serialize(change_stats) if change_stats is not None else None
        normalized_result = (result or "").strip() or None
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO repo_changes(id, repo_id, job_id, summary, change_stats, result, error_message)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    identifier,
                    repo_id,
                    job_id,
                    summary,
                    stats_json,
                    normalized_result,
                    error_message,
                ),
            )
        return identifier

    def list_repo_changes(self, repo_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        if not repo_id:
            return []
        capped = max(1, min(int(limit), 200))
        with self._lock, self._conn:
            rows = self._conn.execute(
                """
                SELECT id, repo_id, job_id, applied_at, summary, change_stats, result, error_message
                  FROM repo_changes
                 WHERE repo_id = ?
              ORDER BY datetime(applied_at) DESC, id DESC
                 LIMIT ?
                """,
                (repo_id, capped),
            ).fetchall()
        items: list[dict[str, Any]] = []
        for row in rows:
            payload = dict(row)
            payload["change_stats"] = _deserialize(payload.get("change_stats"), {})
            items.append(payload)
        return items

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
                    "UPDATE tabs SET shadow_mode=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (shadow_mode, tab_id),
                )

    def update_tab_shadow_mode(self, tab_id: str, mode: str | None) -> None:
        self.ensure_tab(tab_id)
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE tabs SET shadow_mode=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
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

    def _format_tab_row(self, row: Mapping[str, Any]) -> dict[str, Any]:
        payload = dict(row)
        current_history = {
            "id": payload.get("current_history_id"),
            "url": payload.get("history_url") or payload.get("current_url"),
            "title": payload.get("history_title") or payload.get("current_title"),
            "visited_at": payload.get("history_visited_at") or payload.get("last_visited_at"),
        }
        if not any(current_history.values()):
            current_history = None
        return {
            "id": payload.get("id"),
            "shadow_mode": payload.get("shadow_mode"),
            "thread_id": payload.get("thread_id"),
            "current_history_id": payload.get("current_history_id"),
            "current_url": payload.get("current_url") or payload.get("history_url"),
            "current_title": payload.get("current_title") or payload.get("history_title"),
            "created_at": payload.get("created_at"),
            "updated_at": payload.get("updated_at"),
            "last_visited_at": payload.get("last_visited_at"),
            "current_history": current_history,
        }

    def list_tabs(self, *, limit: int = 50) -> list[dict[str, Any]]:
        capped = max(1, min(int(limit), 200))
        with self._lock, self._conn:
            rows = self._conn.execute(
                """
                SELECT t.id,
                       t.shadow_mode,
                       t.thread_id,
                       t.current_history_id,
                       t.current_url,
                       t.current_title,
                       t.created_at,
                       t.updated_at,
                       t.last_visited_at,
                       h.url AS history_url,
                       h.title AS history_title,
                       h.visited_at AS history_visited_at
                  FROM tabs AS t
             LEFT JOIN history AS h ON h.id = t.current_history_id
              ORDER BY COALESCE(t.updated_at, t.created_at) DESC
                 LIMIT ?
                """,
                (capped,),
            ).fetchall()
        return [self._format_tab_row(row) for row in rows]

    def get_tab(self, tab_id: str) -> dict[str, Any] | None:
        if not tab_id:
            return None
        with self._lock, self._conn:
            row = self._conn.execute(
                """
                SELECT t.id,
                       t.shadow_mode,
                       t.thread_id,
                       t.current_history_id,
                       t.current_url,
                       t.current_title,
                       t.created_at,
                       t.updated_at,
                       t.last_visited_at,
                       h.url AS history_url,
                       h.title AS history_title,
                       h.visited_at AS history_visited_at
                  FROM tabs AS t
             LEFT JOIN history AS h ON h.id = t.current_history_id
                 WHERE t.id = ?
                """,
                (tab_id,),
            ).fetchone()
        if not row:
            return None
        return self._format_tab_row(row)

    def bind_tab_thread(self, tab_id: str, thread_id: str | None) -> None:
        if not tab_id:
            return
        self.ensure_tab(tab_id)
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE tabs SET thread_id = ?, updated_at=CURRENT_TIMESTAMP WHERE id = ?",
                (thread_id, tab_id),
            )

    def tab_thread_id(self, tab_id: str) -> str | None:
        if not tab_id:
            return None
        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT thread_id FROM tabs WHERE id = ?",
                (tab_id,),
            ).fetchone()
        if not row:
            return None
        value = row["thread_id"]
        return str(value) if value else None

    def update_tab_navigation(
        self,
        tab_id: str,
        *,
        history_id: int | None = None,
        url: str | None = None,
        title: str | None = None,
    ) -> None:
        if not tab_id:
            return
        updates: list[str] = ["updated_at = CURRENT_TIMESTAMP"]
        params: list[Any] = []
        if history_id is not None:
            updates.append("current_history_id = ?")
            params.append(history_id)
            updates.append("last_visited_at = CURRENT_TIMESTAMP")
        if url is not None:
            updates.append("current_url = ?")
            params.append(url)
        if title is not None:
            updates.append("current_title = ?")
            params.append(title)
        if len(updates) == 1:
            return
        self.ensure_tab(tab_id)
        params.append(tab_id)
        with self._lock, self._conn:
            self._conn.execute(
                f"UPDATE tabs SET {', '.join(updates)} WHERE id = ?",
                params,
            )

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
                (
                    tab_id,
                    url,
                    title,
                    referrer,
                    status_code,
                    content_type,
                    int(bool(shadow_enqueued)),
                ),
            )
            history_id = cursor.lastrowid
        if tab_id:
            self.update_tab_navigation(tab_id, history_id=int(history_id), url=url, title=title)
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

    def purge_history(
        self,
        *,
        domain: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        clear_all: bool = False,
    ) -> int:
        normalized_domain = str(domain or "").strip().lower() or None
        clauses: list[str] = []
        params: list[Any] = []
        if not clear_all and normalized_domain:
            clauses.append("lower(url) LIKE ?")
            params.append(f"%{normalized_domain}%")
        if not clear_all and start:
            clauses.append("visited_at >= ?")
            params.append(start.isoformat())
        if not clear_all and end:
            clauses.append("visited_at <= ?")
            params.append(end.isoformat())
        if not clauses and not clear_all:
            return 0
        condition = " AND ".join(clauses) if clauses else "1=1"
        params_tuple = tuple(params)
        with self._lock, self._conn:
            row = self._conn.execute(
                f"SELECT COUNT(*) FROM history WHERE {condition}", params_tuple
            ).fetchone()
            total = int(row[0] or 0)
            if total == 0:
                return 0
            self._conn.execute(
                f"""
                UPDATE tabs
                   SET current_history_id = NULL
                 WHERE current_history_id IN (
                     SELECT id FROM history WHERE {condition}
                 )
                """,
                params_tuple,
            )
            self._conn.execute(
                f"DELETE FROM history WHERE {condition}", params_tuple
            )
        return total

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

    def export_browser_history(self) -> list[dict[str, Any]]:
        with self._lock, self._conn:
            rows = self._conn.execute(
                """
                SELECT id, tab_id, url, title, visited_at, referrer, status_code, content_type, shadow_enqueued
                  FROM history
              ORDER BY datetime(visited_at) ASC, id ASC
                """
            ).fetchall()
        payload: list[dict[str, Any]] = []
        for row in rows:
            record = dict(row)
            record["shadow_enqueued"] = bool(record.get("shadow_enqueued"))
            payload.append(record)
        return payload

    def import_browser_history_record(self, record: Mapping[str, Any]) -> int:
        url = str(record.get("url") or "").strip()
        if not url:
            raise ValueError("history url is required")
        visited_at = str(record.get("visited_at") or _utc_now())
        tab_id = record.get("tab_id")
        if tab_id is not None:
            tab_id = str(tab_id).strip() or None
        title = record.get("title")
        referrer = record.get("referrer")
        status_code = record.get("status_code")
        content_type = record.get("content_type")
        shadow_enqueued = int(bool(record.get("shadow_enqueued")))
        if tab_id:
            self.ensure_tab(tab_id)
        with self._lock, self._conn:
            existing = self._conn.execute(
                "SELECT id FROM history WHERE url = ? AND visited_at = ? LIMIT 1",
                (url, visited_at),
            ).fetchone()
            if existing:
                return int(existing["id"])
            cursor = self._conn.execute(
                """
                INSERT INTO history(tab_id, url, title, visited_at, referrer, status_code, content_type, shadow_enqueued)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (tab_id, url, title, visited_at, referrer, status_code, content_type, shadow_enqueued),
            )
            history_id = cursor.lastrowid
        if tab_id:
            self.update_tab_navigation(tab_id, history_id=int(history_id), url=url, title=title)
        return int(history_id)

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

    def enabled_seed_urls(
        self, category_keys: Sequence[str] | None = None
    ) -> list[str]:
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

    def overview_counters(self) -> dict[str, Any]:
        def _count(query: str, params: Sequence[Any] | None = None) -> int:
            try:
                row = self._conn.execute(query, params or ()).fetchone()
            except sqlite3.OperationalError:
                return 0
            value = row[0] if row else 0
            try:
                return int(value)
            except (TypeError, ValueError):
                return 0

        with self._lock, self._conn:
            tabs_total = _count("SELECT COUNT(*) FROM tabs")
            tabs_linked = _count(
                "SELECT COUNT(*) FROM tabs WHERE thread_id IS NOT NULL AND thread_id <> ''"
            )
            history_row = self._conn.execute(
                "SELECT COUNT(*), MAX(visited_at) FROM history"
            ).fetchone()
            history_total = int(history_row[0] or 0)
            history_last = history_row[1] if history_row else None
            documents_total = _count("SELECT COUNT(*) FROM documents")
            pages_total = _count("SELECT COUNT(*) FROM pages")
            pending_docs = _count("SELECT COUNT(*) FROM pending_documents")
            pending_chunks = _count("SELECT COUNT(*) FROM pending_chunks")
            pending_vectors = _count("SELECT COUNT(*) FROM pending_vectors_queue")
            llm_threads = _count("SELECT COUNT(*) FROM llm_threads")
            llm_messages = _count("SELECT COUNT(*) FROM llm_messages")
            memories_total = _count("SELECT COUNT(*) FROM memories")
            tasks_total = _count("SELECT COUNT(*) FROM tasks")
            rows = self._conn.execute(
                "SELECT status, COUNT(*) AS total FROM tasks GROUP BY status"
            ).fetchall()
            tasks_by_status = {
                str(row["status"] or "unknown"): int(row["total"] or 0)
                for row in rows
            }

        return {
            "browser": {
                "tabs": {"total": tabs_total, "linked": tabs_linked},
                "history": {"entries": history_total, "last_visit": history_last},
            },
            "knowledge": {
                "documents": documents_total,
                "pages": pages_total,
                "pending_documents": pending_docs,
                "pending_chunks": pending_chunks,
                "pending_vectors": pending_vectors,
            },
            "llm": {
                "threads": {"total": llm_threads},
                "messages": {"total": llm_messages},
                "memories": {"total": memories_total},
            },
            "tasks": {"total": tasks_total, "by_status": tasks_by_status},
        }

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

    def enqueue_seed_jobs(
        self, category_keys: Sequence[str], *, priority: int = 0
    ) -> list[str]:
        urls = self.enabled_seed_urls(category_keys)
        job_ids: list[str] = []
        for url in urls:
            job_ids.append(
                self.enqueue_crawl_job(url, priority=priority, reason="seed")
            )
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
            edge_total = self._conn.execute(
                "SELECT COUNT(*) FROM link_edges"
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
            sample_pages = self._conn.execute(
                """
                SELECT url, title, site, last_seen
                  FROM pages
              ORDER BY datetime(COALESCE(last_seen, first_seen)) DESC
                 LIMIT 5
                """
            ).fetchall()
        clusters = []
        for row in top_sites:
            clusters.append({"site": row["site"], "degree": row["degree"]})
        sample = []
        for row in sample_pages:
            sample.append(
                {
                    "url": row["url"],
                    "title": row["title"],
                    "site": row["site"],
                    "last_seen": row["last_seen"],
                }
            )
        return {
            "pages": int(page_total),
            "sites": int(site_total),
            "fresh_7d": int(fresh),
            "connections": int(edge_total),
            "top_sites": clusters,
            "sample": sample,
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
        indexed_only: bool = False,
    ) -> list[dict[str, Any]]:
        sql = [
            # expose whether a page has an embedding to reflect vector index presence
            "SELECT id, url, site, title, first_seen, last_seen, topics, (embedding IS NOT NULL) AS indexed",
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
        if indexed_only:
            clauses.append("embedding IS NOT NULL")
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
            # coerce SQLite boolean to real bool
            if "indexed" in record:
                try:
                    record["indexed"] = bool(record["indexed"])
                except Exception:
                    record["indexed"] = False
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
        start: datetime | None = None,
        end: datetime | None = None,
        category: str | None = None,
    ) -> list[dict[str, Any]]:
        sql = [
            "SELECT e.src_url, e.dst_url, e.relation",
            "FROM link_edges AS e",
            "LEFT JOIN pages AS ps ON ps.url = e.src_url",
            "LEFT JOIN pages AS pd ON pd.url = e.dst_url",
        ]
        clauses: list[str] = []
        params: list[Any] = []
        if site:
            clauses.append("(ps.site = ? OR pd.site = ?)")
            params.extend([site, site])
        if start:
            clauses.append("((ps.last_seen IS NOT NULL AND ps.last_seen >= ?) OR (pd.last_seen IS NOT NULL AND pd.last_seen >= ?))")
            params.extend([start.isoformat(), start.isoformat()])
        if end:
            clauses.append("((ps.last_seen IS NOT NULL AND ps.last_seen <= ?) OR (pd.last_seen IS NOT NULL AND pd.last_seen <= ?))")
            params.extend([end.isoformat(), end.isoformat()])
        if category:
            clauses.append("((ps.topics IS NOT NULL AND ps.topics LIKE ?) OR (pd.topics IS NOT NULL AND pd.topics LIKE ?))")
            like = f"%{category}%"
            params.extend([like, like])
        if clauses:
            sql.append("WHERE " + " AND ".join(clauses))
        sql.append("LIMIT ?")
        params.append(max(1, min(limit, 2000)))
        query_sql = " ".join(sql)
        with self._lock, self._conn:
            rows = self._conn.execute(query_sql, params).fetchall()
        return [
            {"src_url": row["src_url"], "dst_url": row["dst_url"], "relation": row["relation"]}
            for row in rows
        ]

    # -------------------------------
    # Site-level graph (overview)
    # -------------------------------
    def graph_site_nodes(
        self,
        *,
        limit: int = 200,
        start: datetime | None = None,
        end: datetime | None = None,
        min_degree: int = 0,
    ) -> list[dict[str, Any]]:
        seven_days_ago = datetime.utcnow() - timedelta(days=7)
        page_sql = [
            "SELECT site, COUNT(*) AS pages, MAX(last_seen) AS last_seen,",
            "SUM(CASE WHEN last_seen IS NOT NULL AND last_seen >= ? THEN 1 ELSE 0 END) AS fresh_7d",
            "FROM pages WHERE site IS NOT NULL",
        ]
        params: list[Any] = [seven_days_ago.isoformat()]
        if start:
            page_sql.append("AND last_seen >= ?")
            params.append(start.isoformat())
        if end:
            page_sql.append("AND last_seen <= ?")
            params.append(end.isoformat())
        page_sql.append("GROUP BY site ORDER BY pages DESC LIMIT ?")
        params.append(max(1, min(limit, 2000)))
        page_query = " ".join(page_sql)

        degree_query = (
            "SELECT p.site AS site, COUNT(*) AS degree "
            "FROM link_edges AS e JOIN pages AS p ON (p.url = e.src_url OR p.url = e.dst_url) "
            "WHERE p.site IS NOT NULL GROUP BY p.site"
        )

        with self._lock, self._conn:
            page_rows = self._conn.execute(page_query, params).fetchall()
            degree_rows = self._conn.execute(degree_query).fetchall()

        degree_map: dict[str, int] = {str(r["site"]): int(r["degree"]) for r in degree_rows}
        results: list[dict[str, Any]] = []
        for row in page_rows:
            site = str(row["site"])
            degree = int(degree_map.get(site, 0))
            if min_degree > 0 and degree < min_degree:
                continue
            results.append(
                {
                    "id": site,
                    "site": site,
                    "pages": int(row["pages"] or 0),
                    "degree": degree,
                    "fresh_7d": int(row["fresh_7d"] or 0),
                    "last_seen": row["last_seen"],
                }
            )
        return results

    def graph_site_edges(
        self,
        *,
        limit: int = 1000,
        start: datetime | None = None,
        end: datetime | None = None,
        min_weight: int = 1,
    ) -> list[dict[str, Any]]:
        sql = [
            "SELECT ps.site AS src_site, pd.site AS dst_site, COUNT(*) AS weight",
            "FROM link_edges AS e",
            "JOIN pages AS ps ON ps.url = e.src_url",
            "JOIN pages AS pd ON pd.url = e.dst_url",
            "WHERE ps.site IS NOT NULL AND pd.site IS NOT NULL AND ps.site != pd.site",
        ]
        params: list[Any] = []
        if start:
            sql.append("AND ps.last_seen >= ?")
            params.append(start.isoformat())
        if end:
            sql.append("AND ps.last_seen <= ?")
            params.append(end.isoformat())
        sql.append("GROUP BY ps.site, pd.site HAVING COUNT(*) >= ? ORDER BY weight DESC LIMIT ?")
        params.extend([max(1, min_weight), max(1, min(limit, 5000))])
        query_sql = " ".join(sql)
        with self._lock, self._conn:
            rows = self._conn.execute(query_sql, params).fetchall()
        return [
            {"src_site": row["src_site"], "dst_site": row["dst_site"], "weight": int(row["weight"] or 0)}
            for row in rows
        ]

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
                (
                    job_id,
                    seed,
                    query,
                    normalized_path,
                    parent_url,
                    int(bool(is_source)),
                ),
            )

    def pending_crawl_jobs(self) -> list[dict[str, Any]]:
        with self._lock, self._conn:
            rows = self._conn.execute(
                "SELECT id, query, seed, status FROM crawl_jobs WHERE status IN ('queued','running')"
            ).fetchall()
        return [dict(row) for row in rows]

    def update_crawl_status(
        self,
        job_id: str,
        status: str,
        *,
        stats: Mapping[str, Any] | None = None,
        error: str | None = None,
        preview: Iterable[Mapping[str, Any]] | None = None,
        normalized_path: str | None = None,
    ) -> None:
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
                (
                    status,
                    error,
                    stats_payload,
                    normalized_path,
                    preview_payload,
                    job_id,
                ),
            )

    def record_crawl_event(
        self, job_id: str, stage: str, payload: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
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
        outlinks: Iterable[str] | None = None,
    ) -> None:
        categories_json = _serialize(_ensure_list(categories or []))
        labels_json = _serialize(_ensure_list(labels or []))
        verification_json = (
            _serialize(verification) if verification is not None else None
        )
        site_value = _normalize_site(site) or _normalize_site(url)
        try:
            last_seen = (
                datetime.fromtimestamp(float(fetched_at), tz=timezone.utc).isoformat(
                    timespec="seconds"
                )
                if fetched_at is not None
                else _utc_now()
            )
        except (TypeError, ValueError):
            last_seen = _utc_now()
        outlinks_normalized = _normalize_links(outlinks)
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
                    site_value,
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
            try:
                self._conn.execute(
                    """
                    INSERT INTO pages(url, site, title, first_seen, last_seen, topics, embedding)
                    VALUES(?, ?, ?, ?, ?, ?, NULL)
                    ON CONFLICT(url) DO UPDATE SET
                        site = COALESCE(excluded.site, pages.site),
                        title = COALESCE(NULLIF(excluded.title, ''), COALESCE(pages.title, excluded.url)),
                        last_seen = excluded.last_seen,
                        topics = CASE
                            WHEN excluded.topics IS NOT NULL AND excluded.topics != '[]' THEN excluded.topics
                            ELSE pages.topics
                        END
                    """,
                    (
                        url,
                        site_value,
                        title or url,
                        last_seen,
                        last_seen,
                        categories_json,
                    ),
                )
                if outlinks_normalized:
                    for link in outlinks_normalized:
                        self._conn.execute(
                            """
                            INSERT OR IGNORE INTO link_edges(src_url, dst_url, relation)
                            VALUES (?, ?, 'link')
                            """,
                            (url, link),
                        )
            except Exception:  # pragma: no cover - defensive logging only
                LOGGER.debug("failed to persist page/link graph for %s", url, exc_info=True)

    # ------------------------------------------------------------------
    # Domain profiles
    # ------------------------------------------------------------------
    def count_documents_for_site(self, site: str) -> int:
        """Return the number of documents recorded for ``site``."""

        normalized = (site or "").strip().lower()
        if not normalized:
            return 0

        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT COUNT(*) AS total FROM documents WHERE site = ?",
                (normalized,),
            ).fetchone()
            total = int(row["total"] if row else 0)
            if total > 0:
                return total
            fallback_pattern = f"%://{normalized}/%"
            fallback_row = self._conn.execute(
                "SELECT COUNT(*) AS total FROM documents WHERE url LIKE ?",
                (fallback_pattern,),
            ).fetchone()
        return int(fallback_row["total"] if fallback_row else 0)

    def list_known_subdomains(self, host: str, limit: int = 10) -> list[str]:
        """Return distinct subdomains rooted under ``host`` observed in documents."""

        normalized = (host or "").strip().lower()
        if not normalized:
            return []
        limit_value = max(1, min(int(limit or 1), 50))
        pattern = f"%.{normalized}"
        with self._lock, self._conn:
            rows = self._conn.execute(
                """
                SELECT DISTINCT site
                FROM documents
                WHERE site LIKE ?
                ORDER BY site ASC
                LIMIT ?
                """,
                (pattern, limit_value),
            ).fetchall()
        subdomains: list[str] = []
        for row in rows:
            value = row["site"] if isinstance(row, Mapping) else row[0]
            if not value:
                continue
            text = str(value).strip().lower()
            if text and text != normalized:
                subdomains.append(text)
        return subdomains

    def upsert_domain_profile(
        self,
        *,
        host: str,
        pages_cached: int,
        robots_txt: str | None,
        robots_allows: int,
        robots_disallows: int,
        requires_account: bool,
        clearance: str,
        sitemaps: Sequence[str] | None,
        subdomains: Sequence[str] | None,
        last_scanned: float | None,
    ) -> None:
        normalized = (host or "").strip().lower()
        if not normalized:
            return

        def _clean_list(values: Sequence[str] | None) -> list[str]:
            cleaned: list[str] = []
            if not values:
                return cleaned
            seen: set[str] = set()
            for value in values:
                text = str(value).strip()
                if not text:
                    continue
                lowered = text.lower()
                if lowered in seen:
                    continue
                seen.add(lowered)
                cleaned.append(text)
            return cleaned

        serialized_sitemaps = _serialize(_clean_list(sitemaps))
        serialized_subdomains = _serialize(_clean_list(subdomains))
        robots_text = (robots_txt or "").strip() or None
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO domain_profiles(
                    host, pages_cached, robots_txt, robots_allows, robots_disallows,
                    requires_account, clearance, sitemaps, subdomains, last_scanned
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(host) DO UPDATE SET
                    pages_cached = excluded.pages_cached,
                    robots_txt = excluded.robots_txt,
                    robots_allows = excluded.robots_allows,
                    robots_disallows = excluded.robots_disallows,
                    requires_account = excluded.requires_account,
                    clearance = excluded.clearance,
                    sitemaps = excluded.sitemaps,
                    subdomains = excluded.subdomains,
                    last_scanned = excluded.last_scanned
                """,
                (
                    normalized,
                    int(pages_cached),
                    robots_text,
                    int(robots_allows),
                    int(robots_disallows),
                    1 if requires_account else 0,
                    (clearance or "public").strip() or "public",
                    serialized_sitemaps,
                    serialized_subdomains,
                    float(last_scanned) if last_scanned is not None else None,
                ),
            )

    def get_domain_profile(self, host: str) -> dict[str, Any] | None:
        normalized = (host or "").strip().lower()
        if not normalized:
            return None
        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT * FROM domain_profiles WHERE host = ?",
                (normalized,),
            ).fetchone()
        if not row:
            return None
        payload = dict(row)
        payload["requires_account"] = bool(payload.get("requires_account"))
        payload["sitemaps"] = _deserialize(payload.get("sitemaps"), [])
        payload["subdomains"] = _deserialize(payload.get("subdomains"), [])
        return payload

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
            "tables": {
                table: dict(columns) for table, columns in snapshot.tables.items()
            },
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
            "domain_profiles": {
                "host": "TEXT",
                "pages_cached": "INTEGER",
                "robots_txt": "TEXT",
                "robots_allows": "INTEGER",
                "robots_disallows": "INTEGER",
                "requires_account": "INTEGER",
                "clearance": "TEXT",
                "sitemaps": "TEXT",
                "subdomains": "TEXT",
                "last_scanned": "REAL",
            },
            "llm_threads": {
                "id": "TEXT",
                "title": "TEXT",
                "description": "TEXT",
                "origin": "TEXT",
                "created_at": "TEXT",
                "updated_at": "TEXT",
                "last_user_message_at": "TEXT",
                "last_assistant_message_at": "TEXT",
                "metadata": "TEXT",
            },
            "llm_messages": {
                "id": "TEXT",
                "thread_id": "TEXT",
                "parent_id": "TEXT",
                "role": "TEXT",
                "content": "TEXT",
                "created_at": "TEXT",
                "tokens": "INTEGER",
                "metadata": "TEXT",
            },
            "tasks": {
                "id": "TEXT",
                "thread_id": "TEXT",
                "title": "TEXT",
                "description": "TEXT",
                "status": "TEXT",
                "priority": "INTEGER",
                "due_at": "TEXT",
                "created_at": "TEXT",
                "updated_at": "TEXT",
                "closed_at": "TEXT",
                "owner": "TEXT",
                "metadata": "TEXT",
                "result": "TEXT",
            },
            "task_events": {
                "id": "TEXT",
                "task_id": "TEXT",
                "event_type": "TEXT",
                "payload": "TEXT",
                "created_at": "TEXT",
            },
            "memories": {
                "id": "TEXT",
                "scope": "TEXT",
                "scope_ref": "TEXT",
                "key": "TEXT",
                "value": "TEXT",
                "metadata": "TEXT",
                "strength": "REAL",
                "last_accessed": "DATETIME",
                "created_at": "DATETIME",
                "thread_id": "TEXT",
                "task_id": "TEXT",
                "source_message_id": "TEXT",
                "embedding_ref": "TEXT",
            },
            "memory_embeddings": {
                "memory_id": "TEXT",
                "embedding": "BLOB",
                "dim": "INTEGER",
                "vector_ref": "TEXT",
                "created_at": "TEXT",
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

    def resolve_missing_source(
        self, parent_url: str, source_url: str, *, notes: str | None = None
    ) -> None:
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
        next_attempt = int(math.ceil(now + max(1.0, float(delay))))
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
            self._conn.execute(
                "DELETE FROM pending_documents WHERE doc_id = ?", (doc_id,)
            )

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
    # Jobs ledger
    # ------------------------------------------------------------------
    def create_job(
        self,
        job_type: str,
        *,
        status: str = "queued",
        payload: Mapping[str, Any] | None = None,
        task_id: str | None = None,
        thread_id: str | None = None,
        job_id: str | None = None,
    ) -> str:
        normalized_type = (job_type or "generic").strip() or "generic"
        normalized_status = status if status in JOB_STATUSES else "queued"
        identifier = job_id or uuid.uuid4().hex
        payload_json = _serialize(payload) if payload is not None else None
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO jobs(id, type, status, payload, task_id, thread_id)
                VALUES(?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    type = excluded.type,
                    status = excluded.status,
                    payload = COALESCE(excluded.payload, jobs.payload),
                    task_id = COALESCE(excluded.task_id, jobs.task_id),
                    thread_id = COALESCE(excluded.thread_id, jobs.thread_id),
                    updated_at = CURRENT_TIMESTAMP
                """,
                (identifier, normalized_type, normalized_status, payload_json, task_id, thread_id),
            )
        return identifier

    def update_job(
        self,
        job_id: str,
        *,
        status: str | None = None,
        payload: Mapping[str, Any] | None = None,
        result: Mapping[str, Any] | None = None,
        error: str | None = None,
        started_at: str | None = None,
        completed_at: str | None = None,
        task_id: str | None = None,
        thread_id: str | None = None,
    ) -> dict[str, Any] | None:
        sets: list[str] = []
        params: list[Any] = []
        if status:
            normalized_status = status if status in JOB_STATUSES else "queued"
            sets.append("status = ?")
            params.append(normalized_status)
        if payload is not None:
            sets.append("payload = ?")
            params.append(_serialize(payload))
        if result is not None:
            sets.append("result = ?")
            params.append(_serialize(result))
        if error is not None:
            sets.append("error = ?")
            params.append(str(error))
        if started_at is not None:
            sets.append("started_at = ?")
            params.append(started_at)
        if completed_at is not None:
            sets.append("completed_at = ?")
            params.append(completed_at)
        if task_id is not None:
            sets.append("task_id = ?")
            params.append(task_id)
        if thread_id is not None:
            sets.append("thread_id = ?")
            params.append(thread_id)
        sets.append("updated_at = ?")
        params.append(_utc_now())
        params.append(job_id)
        with self._lock, self._conn:
            self._conn.execute(
                f"UPDATE jobs SET {', '.join(sets)} WHERE id = ?",
                params,
            )
        return self.get_job(job_id)

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._lock, self._conn:
            row = self._conn.execute(
                """
                SELECT id, type, status, created_at, updated_at, started_at, completed_at,
                       payload, result, error, task_id, thread_id
                  FROM jobs
                 WHERE id = ?
                """,
                (job_id,),
            ).fetchone()
        if not row:
            return None
        payload = dict(row)
        payload["payload"] = _deserialize(payload.get("payload"), {})
        payload["result"] = _deserialize(payload.get("result"), {})
        return payload

    def list_jobs(
        self,
        *,
        limit: int = 50,
        status: str | None = None,
        job_type: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses = []
        params: list[Any] = []
        if status and status in JOB_STATUSES:
            clauses.append("status = ?")
            params.append(status)
        if job_type:
            clauses.append("type = ?")
            params.append(job_type)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        capped = max(1, min(int(limit), 200))
        query = (
            "SELECT id, type, status, created_at, updated_at, started_at, completed_at, payload, result, error, task_id, thread_id"
            " FROM jobs"
            + where
            + " ORDER BY datetime(updated_at) DESC LIMIT ?"
        )
        params.append(capped)
        with self._lock, self._conn:
            rows = self._conn.execute(query, params).fetchall()
        items: list[dict[str, Any]] = []
        for row in rows:
            record = dict(row)
            record["payload"] = _deserialize(record.get("payload"), {})
            record["result"] = _deserialize(record.get("result"), {})
            items.append(record)
        return items

    def prune_jobs(
        self, *, statuses: Iterable[str] | None = None, older_than_days: int = 30
    ) -> int:
        candidates = [
            (status or "").strip().lower()
            for status in (statuses or [])
            if isinstance(status, str)
        ]
        allowed = {status for status in candidates if status in JOB_STATUSES}
        if not allowed:
            allowed = {"succeeded"}
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=max(1, older_than_days))
        cutoff_iso = cutoff.isoformat(timespec="seconds")
        placeholders = ",".join("?" for _ in allowed)
        params = tuple(list(allowed) + [cutoff_iso])
        with self._lock, self._conn:
            self._conn.execute(
                f"""
                DELETE FROM job_status
                 WHERE job_id IN (
                     SELECT id FROM jobs
                      WHERE status IN ({placeholders})
                        AND COALESCE(completed_at, updated_at, created_at) < ?
                 )
                """,
                params,
            )
            cursor = self._conn.execute(
                f"""
                DELETE FROM jobs
                 WHERE status IN ({placeholders})
                   AND COALESCE(completed_at, updated_at, created_at) < ?
                """,
                params,
            )
        return cursor.rowcount

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

    def list_documents(
        self, *, query: str | None = None, site: str | None = None, limit: int = 100
    ) -> list[DocumentRecord]:
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
        row = self._conn.execute(
            "SELECT * FROM documents WHERE id = ?", (document_id,)
        ).fetchone()
        if not row:
            return None
        payload = dict(row)
        payload["categories"] = _ensure_list(
            _deserialize(payload.get("categories"), [])
        )
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
    def record_visit(
        self, url: str, *, referer: str | None, dur_ms: int | None, source: str
    ) -> None:
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

    def add_chat_message(
        self,
        *,
        message_id: str | None,
        thread_id: str,
        role: str,
        content: str,
        tokens: int | None = None,
    ) -> str:
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

    def recent_messages(
        self, thread_id: str, *, limit: int = 20
    ) -> list[dict[str, Any]]:
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

    def upsert_summary(
        self, thread_id: str, *, summary: str, embedding_ref: str | None = None
    ) -> None:
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
        thread_id: str | None = None,
        task_id: str | None = None,
        source_message_id: str | None = None,
        embedding_ref: str | None = None,
    ) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO memories(id, scope, scope_ref, key, value, metadata, strength, thread_id, task_id, source_message_id, embedding_ref)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    scope = excluded.scope,
                    scope_ref = excluded.scope_ref,
                    key = excluded.key,
                    value = excluded.value,
                    metadata = excluded.metadata,
                    strength = excluded.strength,
                    thread_id = excluded.thread_id,
                    task_id = excluded.task_id,
                    source_message_id = excluded.source_message_id,
                    embedding_ref = excluded.embedding_ref,
                    last_accessed = CURRENT_TIMESTAMP
                """,
                (
                    memory_id,
                    scope,
                    scope_ref,
                    key,
                    value,
                    _serialize(metadata or {}),
                    strength,
                    thread_id,
                    task_id,
                    source_message_id,
                    embedding_ref,
                ),
            )
            self._conn.execute(
                "INSERT INTO memory_audit(memory_id, action, detail) VALUES(?, 'upsert', ?)",
                (memory_id, value[:2000]),
            )

    def list_memories(
        self, *, scope: str, scope_ref: str | None = None, limit: int = 20
    ) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT id, scope, scope_ref, key, value, metadata, strength, last_accessed, created_at,
                   thread_id, task_id, source_message_id, embedding_ref
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

    def search_memories(
        self,
        *,
        query: str | None = None,
        scope: str | None = None,
        scope_ref: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if scope:
            clauses.append("scope = ?")
            params.append(scope)
        if scope_ref:
            clauses.append("scope_ref = ?")
            params.append(scope_ref)
        if query:
            pattern = f"%{query.lower()}%"
            clauses.append("(lower(value) LIKE ? OR lower(COALESCE(key,'')) LIKE ?)")
            params.extend([pattern, pattern])
        where_clause = " WHERE " + " AND ".join(clauses) if clauses else ""
        sql = (
            "SELECT id, scope, scope_ref, key, value, metadata, strength, last_accessed, created_at, "
            "thread_id, task_id, source_message_id, embedding_ref FROM memories"
            + where_clause
            + " ORDER BY last_accessed DESC LIMIT ?"
        )
        params.append(max(1, min(int(limit), 200)))
        rows = self._conn.execute(sql, params).fetchall()
        items: list[dict[str, Any]] = []
        for row in rows:
            payload = dict(row)
            payload["metadata"] = _deserialize(payload.get("metadata"), {})
            items.append(payload)
        return items

    # ------------------------------------------------------------------
    # HydraFlow threads & messages
    # ------------------------------------------------------------------
    def ensure_llm_thread(
        self,
        thread_id: str,
        *,
        title: str | None = None,
        description: str | None = None,
        origin: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> str:
        if not thread_id:
            raise ValueError("thread_id is required")
        created_at = _utc_now()
        metadata_json = _serialize(metadata) if metadata is not None else None
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO llm_threads(id, title, description, origin, created_at, updated_at, metadata)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title = COALESCE(excluded.title, llm_threads.title),
                    description = COALESCE(excluded.description, llm_threads.description),
                    origin = COALESCE(excluded.origin, llm_threads.origin),
                    metadata = COALESCE(excluded.metadata, llm_threads.metadata),
                    updated_at = CURRENT_TIMESTAMP
                """,
                (thread_id, title, description, origin, created_at, created_at, metadata_json),
            )
        return thread_id

    def create_llm_thread(
        self,
        *,
        title: str | None = None,
        description: str | None = None,
        origin: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> str:
        thread_id = uuid.uuid4().hex
        return self.ensure_llm_thread(
            thread_id,
            title=title,
            description=description,
            origin=origin,
            metadata=metadata,
        )

    def get_llm_thread(self, thread_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            """
            SELECT id, title, description, origin, created_at, updated_at,
                   last_user_message_at, last_assistant_message_at, metadata
              FROM llm_threads
             WHERE id = ?
            """,
            (thread_id,),
        ).fetchone()
        if not row:
            return None
        payload = dict(row)
        payload["metadata"] = _deserialize(payload.get("metadata"), {})
        return payload

    def list_llm_threads(
        self, *, limit: int = 50, offset: int = 0
    ) -> list[dict[str, Any]]:
        capped = max(1, min(int(limit), 200))
        start = max(0, int(offset))
        rows = self._conn.execute(
            """
            SELECT id, title, description, origin, created_at, updated_at,
                   last_user_message_at, last_assistant_message_at, metadata
              FROM llm_threads
          ORDER BY COALESCE(updated_at, created_at) DESC
             LIMIT ? OFFSET ?
            """,
            (capped, start),
        ).fetchall()
        items: list[dict[str, Any]] = []
        for row in rows:
            payload = dict(row)
            payload["metadata"] = _deserialize(payload.get("metadata"), {})
            items.append(payload)
        return items

    def export_llm_threads(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT id, title, description, origin, created_at, updated_at,
                   last_user_message_at, last_assistant_message_at, metadata
              FROM llm_threads
          ORDER BY datetime(created_at) ASC
            """
        ).fetchall()
        items: list[dict[str, Any]] = []
        for row in rows:
            payload = dict(row)
            payload["metadata"] = _deserialize(payload.get("metadata"), {})
            items.append(payload)
        return items

    def append_llm_message(
        self,
        *,
        thread_id: str,
        role: str,
        content: str,
        message_id: str | None = None,
        parent_id: str | None = None,
        tokens: int | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> str:
        normalized_role = (role or "").strip().lower() or "user"
        created_at = _utc_now()
        metadata_json = _serialize(metadata) if metadata is not None else None
        msg_id = message_id or uuid.uuid4().hex
        self.ensure_llm_thread(thread_id)
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO llm_messages(id, thread_id, parent_id, role, content, created_at, tokens, metadata)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    thread_id = excluded.thread_id,
                    parent_id = excluded.parent_id,
                    role = excluded.role,
                    content = excluded.content,
                    created_at = excluded.created_at,
                    tokens = excluded.tokens,
                    metadata = excluded.metadata
                """,
                (msg_id, thread_id, parent_id, normalized_role, content, created_at, tokens, metadata_json),
            )
            updates = [created_at]
            set_fragments = ["updated_at = ?"]
            if normalized_role == "user":
                set_fragments.append("last_user_message_at = ?")
                updates.append(created_at)
            elif normalized_role == "assistant":
                set_fragments.append("last_assistant_message_at = ?")
                updates.append(created_at)
            updates.append(thread_id)
            self._conn.execute(
                f"UPDATE llm_threads SET {', '.join(set_fragments)} WHERE id = ?",
                updates,
            )
        return msg_id

    def delete_llm_thread(self, thread_id: str) -> dict[str, int]:
        stats = {"threads": 0, "messages": 0, "tasks": 0, "memories": 0, "tabs": 0}
        if not thread_id:
            return stats
        with self._lock, self._conn:
            exists = self._conn.execute(
                "SELECT 1 FROM llm_threads WHERE id=?", (thread_id,)
            ).fetchone()
            if not exists:
                return stats
            stats["messages"] = int(
                self._conn.execute(
                    "SELECT COUNT(*) FROM llm_messages WHERE thread_id=?",
                    (thread_id,),
                ).fetchone()[0]
                or 0
            )
            stats["tasks"] = int(
                self._conn.execute(
                    "SELECT COUNT(*) FROM tasks WHERE thread_id=?",
                    (thread_id,),
                ).fetchone()[0]
                or 0
            )
            stats["memories"] = int(
                self._conn.execute(
                    "SELECT COUNT(*) FROM memories WHERE thread_id=?",
                    (thread_id,),
                ).fetchone()[0]
                or 0
            )
            stats["tabs"] = self._conn.execute(
                "UPDATE tabs SET thread_id=NULL WHERE thread_id=?",
                (thread_id,),
            ).rowcount
            self._conn.execute("DELETE FROM tasks WHERE thread_id=?", (thread_id,))
            self._conn.execute("DELETE FROM memories WHERE thread_id=?", (thread_id,))
            stats["threads"] = self._conn.execute(
                "DELETE FROM llm_threads WHERE id=?", (thread_id,)
            ).rowcount
        return stats

    def list_llm_messages(
        self, thread_id: str, *, limit: int = 50, ascending: bool = True
    ) -> list[dict[str, Any]]:
        if not thread_id:
            return []
        capped = max(1, min(int(limit), 200))
        order = "ASC" if ascending else "DESC"
        rows = self._conn.execute(
            f"""
            SELECT id, thread_id, parent_id, role, content, created_at, tokens, metadata
              FROM llm_messages
             WHERE thread_id = ?
          ORDER BY datetime(created_at) {order}
             LIMIT ?
            """,
            (thread_id, capped),
        ).fetchall()
        items: list[dict[str, Any]] = [dict(row) for row in rows]
        for item in items:
            item["metadata"] = _deserialize(item.get("metadata"), {})
        if not ascending:
            return items
        return items

    def export_llm_messages(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT id, thread_id, parent_id, role, content, created_at, tokens, metadata
              FROM llm_messages
          ORDER BY datetime(created_at) ASC
            """
        ).fetchall()
        items: list[dict[str, Any]] = []
        for row in rows:
            payload = dict(row)
            payload["metadata"] = _deserialize(payload.get("metadata"), {})
            items.append(payload)
        return items

    def get_llm_message(self, message_id: str) -> dict[str, Any] | None:
        if not message_id:
            return None
        row = self._conn.execute(
            """
            SELECT id, thread_id, parent_id, role, content, created_at, tokens, metadata
              FROM llm_messages
             WHERE id = ?
            """,
            (message_id,),
        ).fetchone()
        if not row:
            return None
        payload = dict(row)
        payload["metadata"] = _deserialize(payload.get("metadata"), {})
        return payload

    def import_llm_thread_record(self, record: Mapping[str, Any]) -> str:
        identifier = str(record.get("id") or "").strip()
        if not identifier:
            raise ValueError("thread record id required")
        created_at = record.get("created_at") or _utc_now()
        updated_at = record.get("updated_at") or created_at
        metadata_json = _serialize(record.get("metadata")) if record.get("metadata") is not None else None
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO llm_threads(
                    id, title, description, origin, created_at, updated_at,
                    last_user_message_at, last_assistant_message_at, metadata
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title = excluded.title,
                    description = excluded.description,
                    origin = excluded.origin,
                    metadata = COALESCE(excluded.metadata, llm_threads.metadata),
                    last_user_message_at = COALESCE(excluded.last_user_message_at, llm_threads.last_user_message_at),
                    last_assistant_message_at = COALESCE(excluded.last_assistant_message_at, llm_threads.last_assistant_message_at),
                    updated_at = excluded.updated_at
                """,
                (
                    identifier,
                    record.get("title"),
                    record.get("description"),
                    record.get("origin"),
                    created_at,
                    updated_at,
                    record.get("last_user_message_at"),
                    record.get("last_assistant_message_at"),
                    metadata_json,
                ),
            )
        return identifier

    def _find_message_by_timestamp(
        self, thread_id: str, created_at: str | None
    ) -> str | None:
        if not thread_id or not created_at:
            return None
        row = self._conn.execute(
            "SELECT id FROM llm_messages WHERE thread_id = ? AND created_at = ? LIMIT 1",
            (thread_id, created_at),
        ).fetchone()
        if not row:
            return None
        return str(row["id"])

    def import_llm_message_record(self, record: Mapping[str, Any]) -> str:
        thread_id = str(record.get("thread_id") or "").strip()
        if not thread_id:
            raise ValueError("thread_id is required for messages")
        content = record.get("content")
        if content is None:
            raise ValueError("message content is required")
        message_id = str(record.get("id") or "").strip() or None
        created_at = record.get("created_at") or _utc_now()
        self.ensure_llm_thread(thread_id)
        if message_id and self.get_llm_message(message_id):
            return message_id
        dedup = self._find_message_by_timestamp(thread_id, created_at)
        if dedup:
            return dedup
        metadata_json = _serialize(record.get("metadata")) if record.get("metadata") is not None else None
        msg_id = message_id or uuid.uuid4().hex
        role = (record.get("role") or "user").strip().lower() or "user"
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO llm_messages(
                    id, thread_id, parent_id, role, content, created_at, tokens, metadata
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    msg_id,
                    thread_id,
                    record.get("parent_id"),
                    role,
                    content,
                    created_at,
                    record.get("tokens"),
                    metadata_json,
                ),
            )
            self._conn.execute(
                "UPDATE llm_threads SET updated_at = ?, last_user_message_at = CASE WHEN ? = 'user' THEN ? ELSE last_user_message_at END, last_assistant_message_at = CASE WHEN ? = 'assistant' THEN ? ELSE last_assistant_message_at END WHERE id = ?",
                (created_at, role, created_at, role, created_at, thread_id),
            )
        return msg_id

    def recent_llm_messages(
        self, thread_id: str, *, limit: int = 20
    ) -> list[dict[str, Any]]:
        return self.list_llm_messages(thread_id, limit=limit, ascending=True)

    # ------------------------------------------------------------------
    # HydraFlow tasks & events
    # ------------------------------------------------------------------
    def create_task(
        self,
        *,
        title: str,
        description: str | None = None,
        thread_id: str | None = None,
        status: str = "pending",
        priority: int = 0,
        due_at: str | None = None,
        owner: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        result: Mapping[str, Any] | None = None,
    ) -> str:
        task_id = uuid.uuid4().hex
        created_at = _utc_now()
        if thread_id:
            self.ensure_llm_thread(thread_id)
        metadata_json = _serialize(metadata or {})
        result_json = _serialize(result) if result is not None else None
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO tasks(id, thread_id, title, description, status, priority, due_at, created_at, updated_at, owner, metadata, result)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    thread_id,
                    title,
                    description,
                    status,
                    priority,
                    due_at,
                    created_at,
                    created_at,
                    owner,
                    metadata_json,
                    result_json,
                ),
            )
        return task_id

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            """
            SELECT id, thread_id, title, description, status, priority, due_at,
                   created_at, updated_at, closed_at, owner, metadata, result
              FROM tasks
             WHERE id = ?
            """,
            (task_id,),
        ).fetchone()
        if not row:
            return None
        payload = dict(row)
        payload["metadata"] = _deserialize(payload.get("metadata"), {})
        payload["result"] = _deserialize(payload.get("result"), None)
        return payload

    def list_tasks(
        self,
        *,
        status: str | None = None,
        thread_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if thread_id:
            clauses.append("thread_id = ?")
            params.append(thread_id)
        where_clause = " WHERE " + " AND ".join(clauses) if clauses else ""
        sql = (
            "SELECT id, thread_id, title, description, status, priority, due_at, created_at, updated_at, closed_at, owner, metadata, result"
            " FROM tasks"
            + where_clause
            + " ORDER BY updated_at DESC LIMIT ?"
        )
        params.append(max(1, min(int(limit), 200)))
        rows = self._conn.execute(sql, params).fetchall()
        items: list[dict[str, Any]] = []
        for row in rows:
            payload = dict(row)
            payload["metadata"] = _deserialize(payload.get("metadata"), {})
            payload["result"] = _deserialize(payload.get("result"), None)
            items.append(payload)
        return items

    def export_tasks(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT id, thread_id, title, description, status, priority, due_at,
                   created_at, updated_at, closed_at, owner, metadata, result
              FROM tasks
          ORDER BY datetime(created_at) ASC
            """
        ).fetchall()
        items: list[dict[str, Any]] = []
        for row in rows:
            payload = dict(row)
            payload["metadata"] = _deserialize(payload.get("metadata"), {})
            payload["result"] = _deserialize(payload.get("result"), None)
            items.append(payload)
        return items

    def update_task(
        self,
        task_id: str,
        *,
        title: str | None = None,
        description: str | None = None,
        status: str | None = None,
        priority: int | None = None,
        due_at: str | None = None,
        owner: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        result: Mapping[str, Any] | None = None,
        thread_id: str | None = None,
        closed_at: str | None = None,
    ) -> dict[str, Any] | None:
        sets: list[str] = []
        params: list[Any] = []
        updates = {
            "title": title,
            "description": description,
            "status": status,
            "priority": priority,
            "due_at": due_at,
            "owner": owner,
            "thread_id": thread_id,
        }
        for column, value in updates.items():
            if value is None:
                continue
            sets.append(f"{column} = ?")
            params.append(value)
        if metadata is not None:
            sets.append("metadata = ?")
            params.append(_serialize(metadata))
        if result is not None:
            sets.append("result = ?")
            params.append(_serialize(result))
        if closed_at is not None:
            sets.append("closed_at = ?")
            params.append(closed_at)
        if not sets:
            return self.get_task(task_id)
        sets.append("updated_at = ?")
        params.append(_utc_now())
        params.append(task_id)
        with self._lock, self._conn:
            self._conn.execute(
                f"UPDATE tasks SET {', '.join(sets)} WHERE id = ?",
                params,
            )
        return self.get_task(task_id)

    def record_task_event(
        self,
        task_id: str,
        *,
        event_type: str,
        payload: Mapping[str, Any] | None = None,
        event_id: str | None = None,
    ) -> str:
        event_identifier = event_id or uuid.uuid4().hex
        serialized = _serialize(payload or {})
        created_at = _utc_now()
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO task_events(id, task_id, event_type, payload, created_at)
                VALUES(?, ?, ?, ?, ?)
                """,
                (event_identifier, task_id, event_type, serialized, created_at),
            )
        return event_identifier

    def list_task_events(
        self, task_id: str, *, limit: int = 100
    ) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT id, task_id, event_type, payload, created_at
              FROM task_events
             WHERE task_id = ?
          ORDER BY created_at ASC
             LIMIT ?
            """,
            (task_id, max(1, min(int(limit), 500))),
        ).fetchall()
        events: list[dict[str, Any]] = []
        for row in rows:
            payload = dict(row)
            payload["payload"] = _deserialize(payload.get("payload"), {})
            events.append(payload)
        return events

    def import_task_record(self, record: Mapping[str, Any]) -> str:
        identifier = str(record.get("id") or "").strip() or uuid.uuid4().hex
        metadata_json = _serialize(record.get("metadata")) if record.get("metadata") is not None else None
        result_json = _serialize(record.get("result")) if record.get("result") is not None else None
        created_at = record.get("created_at") or _utc_now()
        updated_at = record.get("updated_at") or created_at
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO tasks(
                    id, thread_id, title, description, status, priority, due_at,
                    created_at, updated_at, closed_at, owner, metadata, result
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    thread_id = excluded.thread_id,
                    title = excluded.title,
                    description = excluded.description,
                    status = excluded.status,
                    priority = excluded.priority,
                    due_at = excluded.due_at,
                    closed_at = excluded.closed_at,
                    owner = excluded.owner,
                    metadata = COALESCE(excluded.metadata, tasks.metadata),
                    result = COALESCE(excluded.result, tasks.result),
                    updated_at = excluded.updated_at
                """,
                (
                    identifier,
                    record.get("thread_id"),
                    record.get("title"),
                    record.get("description"),
                    record.get("status") or "pending",
                    record.get("priority") or 0,
                    record.get("due_at"),
                    created_at,
                    updated_at,
                    record.get("closed_at"),
                    record.get("owner"),
                    metadata_json,
                    result_json,
                ),
            )
        return identifier

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
