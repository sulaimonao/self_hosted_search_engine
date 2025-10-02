"""Persistent vector store built on Chroma + DuckDB."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence
import hashlib
import json
import os
import threading

import duckdb
from chromadb.api.models.Collection import Collection
from chromadb.config import Settings

REPO_ROOT = Path(__file__).resolve().parents[2]

os.environ.setdefault("CHROMADB_DISABLE_TELEMETRY", "1")


def _disable_chroma_telemetry() -> None:
    """Best-effort guard to silence Chroma telemetry side-effects."""

    try:  # pragma: no cover - optional dependency internals vary
        import chromadb.telemetry as telemetry_pkg  # type: ignore[import]
    except Exception:  # pragma: no cover - library structure changed
        return

    modules_to_patch: set[Any] = {telemetry_pkg}

    for attr_name, import_path in (
        ("telemetry", "chromadb.telemetry.telemetry"),
        ("product", "chromadb.telemetry.product"),
    ):
        module_attr = getattr(telemetry_pkg, attr_name, None)
        if module_attr is None:
            try:  # pragma: no cover - module renamed/moved
                module_attr = __import__(import_path, fromlist=["_"])  # type: ignore[import]
            except Exception:  # pragma: no cover - ignore if missing
                module_attr = None
        if module_attr is not None:
            modules_to_patch.add(module_attr)

    try:  # pragma: no cover - optional dependency
        import chromadb.telemetry.product.posthog as product_posthog  # type: ignore[import]
    except Exception:
        product_posthog = None
    else:
        modules_to_patch.add(product_posthog)

        posthog_lib = getattr(product_posthog, "posthog", None)
        if posthog_lib is not None:
            modules_to_patch.add(posthog_lib)

    class _NoOpTelemetryClient:
        __slots__ = ()

        def capture(self, *args: Any, **kwargs: Any) -> bool:  # noqa: D401
            return True

    _noop_client = _NoOpTelemetryClient()

    def _patch_module(module: Any) -> None:
        if hasattr(module, "capture"):
            try:
                module.capture = lambda *args, **kwargs: True  # type: ignore[attr-defined]
            except Exception:  # pragma: no cover - guard against readonly attributes
                pass

        telemetry_cls = getattr(module, "Telemetry", None)
        if telemetry_cls is not None and hasattr(telemetry_cls, "capture"):
            try:
                telemetry_cls.capture = lambda self, *args, **kwargs: True  # type: ignore[assignment]
            except Exception:  # pragma: no cover - guard against readonly attributes
                pass

        if hasattr(module, "telemetry_client"):
            try:
                module.telemetry_client = _noop_client  # type: ignore[attr-defined]
            except Exception:  # pragma: no cover - guard against readonly attributes
                pass

        for class_name in ("Telemetry", "Posthog", "ProductTelemetryClient"):
            telemetry_cls = getattr(module, class_name, None)
            if telemetry_cls is not None and hasattr(telemetry_cls, "capture"):
                try:
                    telemetry_cls.capture = lambda self, *args, **kwargs: True  # type: ignore[assignment]
                except Exception:  # pragma: no cover - guard against readonly attributes
                    pass

        get_default = getattr(module, "get_default_client", None)
        if callable(get_default):
            try:
                module.get_default_client = lambda *args, **kwargs: _noop_client  # type: ignore[attr-defined]
            except Exception:  # pragma: no cover - guard against readonly attributes
                pass

    for module in modules_to_patch:
        _patch_module(module)


_disable_chroma_telemetry()

from chromadb import PersistentClient


def _ensure_safe_directory(path: Path, *, label: str) -> Path:
    resolved = path.resolve()
    repo_root = REPO_ROOT.resolve()
    if resolved == repo_root:
        raise ValueError(f"{label} may not be the repository root ({resolved})")
    if resolved == Path(resolved.anchor):
        raise ValueError(f"{label} may not be the filesystem root ({resolved})")
    return path

from ..indexing.chunk import Chunk


@dataclass(slots=True)
class RetrievedChunk:
    """Represents a chunk returned from the vector store."""

    text: str
    title: str | None
    url: str | None
    similarity: float


class VectorStore:
    """Lightweight wrapper around Chroma for RAG retrieval."""

    _COLLECTION_NAME = "rag_documents"
    _client_cache: dict[Path, PersistentClient] = {}
    _collection_cache: dict[Path, Collection] = {}
    _cache_lock = threading.Lock()

    def __init__(self, persist_dir: str | Path, db_path: str | Path) -> None:
        self._persist_dir = _ensure_safe_directory(
            Path(persist_dir).resolve(), label="persist_dir"
        )
        self._db_path = Path(db_path).resolve()
        _ensure_safe_directory(self._db_path.parent, label="db_path parent")
        self._persist_dir.mkdir(parents=True, exist_ok=True)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._collection = self._get_collection(self._persist_dir)
        self._collection_lock = threading.Lock()
        self._initialize_db()

    @classmethod
    def _get_collection(cls, persist_dir: Path) -> Collection:
        key = persist_dir
        with cls._cache_lock:
            collection = cls._collection_cache.get(key)
            if collection is not None:
                return collection
            client = cls._client_cache.get(key)
            if client is None:
                client = PersistentClient(
                    path=str(persist_dir),
                    settings=Settings(
                        anonymized_telemetry=False,
                        allow_reset=True,
                        is_persistent=True,
                    ),
                )
                cls._client_cache[key] = client
            collection = client.get_or_create_collection(
                cls._COLLECTION_NAME, metadata={"hnsw:space": "cosine"}
            )
            cls._collection_cache[key] = collection
            return collection

    def _initialize_db(self) -> None:
        with duckdb.connect(str(self._db_path)) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    url TEXT PRIMARY KEY,
                    title TEXT,
                    etag TEXT,
                    content_hash TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    @staticmethod
    def _chunk_id(url: str, index: int) -> str:
        digest = hashlib.sha1(f"{url}::{index}".encode("utf-8"), usedforsecurity=False)
        return digest.hexdigest()

    @staticmethod
    def _ensure_embedding(vector: Sequence[float]) -> list[float]:
        return [float(value) for value in vector]

    @staticmethod
    def _sanitize_metadata(
        metadata: dict[str, Any]
    ) -> dict[str, str | int | float | bool]:
        """Return a metadata dict limited to Chroma-compatible primitives."""

        sanitized: dict[str, str | int | float | bool] = {}
        for key, value in metadata.items():
            if value is None:
                continue
            if isinstance(value, (list, dict)):
                sanitized[key] = json.dumps(value, ensure_ascii=False)
                continue
            if isinstance(value, (str, int, float, bool)):
                sanitized[key] = value
                continue
            sanitized[key] = str(value)
        return sanitized

    def is_empty(self) -> bool:
        """Return ``True`` when the vector store has no indexed documents."""

        with duckdb.connect(str(self._db_path)) as conn:
            row = conn.execute("SELECT COUNT(*) FROM documents").fetchone()
        doc_count = int(row[0]) if row and row[0] is not None else 0
        if doc_count > 0:
            return False
        try:
            with self._collection_lock:
                collection_total = self._collection.count()
        except Exception:  # pragma: no cover - defensive guard
            return doc_count == 0
        return int(collection_total or 0) == 0

    def needs_update(self, url: str, etag: str | None, content_hash: str) -> bool:
        with duckdb.connect(str(self._db_path)) as conn:
            row = conn.execute(
                "SELECT etag, content_hash FROM documents WHERE url = ?", (url,)
            ).fetchone()
        if row is None:
            return True
        stored_etag, stored_hash = row
        if stored_hash is not None and stored_hash == content_hash:
            return False
        if (
            stored_hash in (None, "")
            and etag is not None
            and stored_etag is not None
            and stored_etag == etag
        ):
            return False
        return True

    def upsert(
        self,
        url: str,
        title: str,
        etag: str | None,
        content_hash: str,
        chunks: Sequence[Chunk],
        embeddings: Sequence[Sequence[float]],
        *,
        metadata: Mapping[str, Any] | None = None,
        doc_id: str | None = None,
    ) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings must have the same length")

        with duckdb.connect(str(self._db_path)) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO documents (url, title, etag, content_hash, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (url, title, etag, content_hash),
            )

        sanitized_metadata = self._sanitize_metadata(dict(metadata or {}))
        document_id = doc_id or url

        with self._collection_lock:
            self._collection.delete(where={"url": url})
            if not chunks:
                return
            documents = [chunk.text for chunk in chunks]
            metadatas = [
                {
                    "url": url,
                    "title": title,
                    "chunk_index": idx,
                    "start": chunk.start,
                    "end": chunk.end,
                    "token_count": chunk.token_count,
                    "etag": etag,
                    "content_hash": content_hash,
                    "doc_id": document_id,
                }
                for idx, chunk in enumerate(chunks)
            ]
            if sanitized_metadata:
                for entry in metadatas:
                    entry.update(sanitized_metadata)
            ids = [self._chunk_id(url, idx) for idx in range(len(chunks))]
            embedding_list = [self._ensure_embedding(embedding) for embedding in embeddings]
            sanitized_metadatas = [
                self._sanitize_metadata(metadata) for metadata in metadatas
            ]
            self._collection.add(
                ids=ids,
                documents=documents,
                metadatas=sanitized_metadatas,
                embeddings=embedding_list,
            )

    def document_count(self) -> int:
        with duckdb.connect(str(self._db_path)) as conn:
            row = conn.execute("SELECT COUNT(*) FROM documents").fetchone()
        return int(row[0]) if row and row[0] is not None else 0

    def embedding_dimensions(self) -> int:
        with self._collection_lock:
            try:
                sample = self._collection.get(limit=1, include=["embeddings"])
            except Exception:  # pragma: no cover - defensive guard against chroma internals
                return 0
        embeddings = sample.get("embeddings") if isinstance(sample, dict) else None
        if not embeddings:
            return 0
        first = embeddings[0] if isinstance(embeddings, list) else None
        if not first:
            return 0
        vector = first[0] if isinstance(first, list) else first
        if not isinstance(vector, Sequence):
            return 0
        return len(vector)

    def query(
        self,
        vector: Sequence[float],
        k: int,
        similarity_threshold: float,
        *,
        filters: Mapping[str, Any] | None = None,
    ) -> list[RetrievedChunk]:
        if k <= 0:
            return []
        if not vector:
            return []
        query_embedding = [self._ensure_embedding(vector)]
        sanitized_filters: dict[str, str | int | float | bool] = {}
        where_clause: dict[str, Any] | None = None
        if filters:
            sanitized_filters = self._sanitize_metadata(dict(filters))
            if sanitized_filters:
                if len(sanitized_filters) == 1:
                    key, value = next(iter(sanitized_filters.items()))
                    where_clause = {key: value}
                else:
                    where_clause = {
                        "$and": [
                            {key: value} for key, value in sanitized_filters.items()
                        ]
                    }
        with self._collection_lock:
            results = self._collection.query(
                query_embeddings=query_embedding,
                n_results=k,
                include=["metadatas", "documents", "distances"],
                where=where_clause,
            )
        ids = results.get("ids") or []
        if not ids:
            return []
        documents = results.get("documents", [[]])[0] or []
        metadatas = results.get("metadatas", [[]])[0] or []
        distances = results.get("distances", [[]])[0] or []
        retrieved: list[RetrievedChunk] = []
        for document, metadata, distance in zip(documents, metadatas, distances):
            if document is None or metadata is None:
                continue
            similarity = 1.0 - float(distance) if distance is not None else 0.0
            if similarity < similarity_threshold:
                continue
            if sanitized_filters and any(
                metadata.get(key) != value for key, value in sanitized_filters.items()
            ):
                continue
            retrieved.append(
                RetrievedChunk(
                    text=document,
                    title=metadata.get("title"),
                    url=metadata.get("url"),
                    similarity=similarity,
                )
            )
        retrieved.sort(key=lambda chunk: chunk.similarity, reverse=True)
        return retrieved[:k]


__all__ = ["VectorStore", "RetrievedChunk"]
