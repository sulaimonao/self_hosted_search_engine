"""High level helpers for the application state database."""

from __future__ import annotations

import json
import threading
import time
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .schema import connect, migrate


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


class AppStateDB:
    """Thin wrapper around SQLite providing typed helpers."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = connect(path)
        migrate(self._conn)
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Crawl jobs
    # ------------------------------------------------------------------
    def record_crawl_job(self, job_id: str, *, seed: str | None = None, query: str | None = None,
                          normalized_path: str | None = None) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO crawl_jobs(id, status, seed, query, normalized_path)
                VALUES(?, 'queued', ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET seed=excluded.seed, query=excluded.query
                """,
                (job_id, seed, query, normalized_path),
            )

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
    ) -> None:
        metadata_json = _serialize(metadata or {})
        now = time.time()
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO pending_documents(doc_id, job_id, url, title, resolved_title, doc_hash, sim_signature, metadata, created_at, updated_at)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(doc_id) DO UPDATE SET
                    job_id = excluded.job_id,
                    url = excluded.url,
                    title = excluded.title,
                    resolved_title = excluded.resolved_title,
                    doc_hash = excluded.doc_hash,
                    sim_signature = excluded.sim_signature,
                    metadata = excluded.metadata,
                    updated_at = ?
                """,
                (
                    doc_id,
                    job_id,
                    url,
                    title,
                    resolved_title,
                    doc_hash,
                    int(sim_signature) if sim_signature is not None else None,
                    metadata_json,
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
                    (doc_id, index, text, _serialize(chunk_metadata or {}), now, now, now),
                )
            next_attempt = max(now + float(initial_delay), now)
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
        now = time.time()
        rows: list[dict[str, Any]] = []
        with self._lock, self._conn:
            cursor = self._conn.execute(
                """
                SELECT q.doc_id, q.attempts, d.job_id, d.url, d.title, d.resolved_title, d.doc_hash, d.sim_signature, d.metadata
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
                        "attempts": row["attempts"],
                        "job_id": row["job_id"],
                        "url": row["url"],
                        "title": row["title"],
                        "resolved_title": row["resolved_title"],
                        "doc_hash": row["doc_hash"],
                        "sim_signature": row["sim_signature"],
                        "metadata": _deserialize(row["metadata"], {}),
                        "chunks": chunks,
                    }
                )
                self._conn.execute(
                    "DELETE FROM pending_vectors_queue WHERE doc_id = ?",
                    (doc_id,),
                )
        return rows

    def reschedule_pending_document(self, doc_id: str, *, delay: float, attempts: int) -> None:
        now = time.time()
        next_attempt = now + max(1.0, float(delay))
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

    def clear_pending_document(self, doc_id: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM pending_documents WHERE doc_id = ?", (doc_id,))

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
