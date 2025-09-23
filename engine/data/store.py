"""Persistent vector store built on Chroma + DuckDB."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence
import hashlib
import threading
import json

import duckdb
from chromadb import PersistentClient
from chromadb.api.models.Collection import Collection
from chromadb.config import Settings

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
        self._persist_dir = Path(persist_dir).resolve()
        self._db_path = Path(db_path).resolve()
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
                }
                for idx, chunk in enumerate(chunks)
            ]
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

    def query(
        self, vector: Sequence[float], k: int, similarity_threshold: float
    ) -> list[RetrievedChunk]:
        if k <= 0:
            return []
        if not vector:
            return []
        query_embedding = [self._ensure_embedding(vector)]
        with self._collection_lock:
            results = self._collection.query(
                query_embeddings=query_embedding,
                n_results=k,
                include=["metadatas", "documents", "distances"],
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
