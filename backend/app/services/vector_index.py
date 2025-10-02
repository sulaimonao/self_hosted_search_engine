"""Vector index orchestration backed by Chroma and Ollama embeddings."""

from __future__ import annotations

import hashlib
import logging
import os
import threading
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from engine.config import EngineConfig
from engine.data.store import VectorStore
from engine.indexing.chunk import TokenChunker
from engine.indexing.embed import EmbeddingError, OllamaEmbedder
from engine.llm.ollama_client import OllamaClient, OllamaClientError

from backend.app.config import AppConfig
from backend.app.indexer.dedupe import SimHashIndex, simhash64
from backend.app.search.embedding import embed_query as _fallback_embed
from backend.app.services import ollama_client as ollama_services
from observability import start_span


LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class IndexResult:
    doc_id: str
    chunks: int
    dims: int
    duplicate_of: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "doc_id": self.doc_id,
            "chunks": self.chunks,
            "dims": self.dims,
        }
        if self.duplicate_of:
            payload["duplicate_of"] = self.duplicate_of
        payload["skipped"] = self.chunks == 0
        return payload


@dataclass(slots=True)
class SearchHit:
    url: str | None
    title: str | None
    chunk: str
    score: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "chunk": self.chunk,
            "score": self.score,
        }


class EmbedderUnavailableError(RuntimeError):
    """Raised when the configured embedding model is not available."""

    def __init__(
        self,
        model: str,
        *,
        detail: str | None = None,
        autopull_started: bool = False,
    ) -> None:
        message = detail or f"Embedding model '{model}' is unavailable"
        super().__init__(message)
        self.model = model
        self.detail = message
        self.autopull_started = autopull_started


class VectorIndexService:
    """High level façade that coordinates embedding + Chroma persistence."""

    _TEST_EMBED_DIMS = 128

    def __init__(
        self,
        *,
        engine_config: EngineConfig,
        app_config: AppConfig,
    ) -> None:
        self._engine_config = engine_config
        self._app_config = app_config
        self._vector_store = VectorStore(
            engine_config.index.persist_dir, engine_config.index.db_path
        )
        self._chunker = TokenChunker()
        self._client = OllamaClient(engine_config.ollama.base_url)
        self._embed_model = (engine_config.models.embed or "embeddinggemma").strip()
        self._similarity_threshold = float(engine_config.retrieval.similarity_threshold)
        self._dev_allow_autopull = bool(app_config.dev_allow_autopull)
        self._autopull_started = False
        self._lock = threading.RLock()
        self._dedupe_path = app_config.agent_data_dir / "vector_simhash.json"
        self._dedupe_path.parent.mkdir(parents=True, exist_ok=True)
        self._simhash_index = SimHashIndex.load(self._dedupe_path)
        self._last_dims = 0
        self._test_mode = os.getenv("EMBED_TEST_MODE", "0").lower() in {
            "1",
            "true",
            "on",
        }
        self._embedder: OllamaEmbedder | None = None
        if not self._test_mode:
            self._embedder = OllamaEmbedder(self._client, self._embed_model)
        LOGGER.debug(
            "vector index initialised (test_mode=%s, model=%s)",
            self._test_mode,
            self._embed_model,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def upsert_document(
        self,
        *,
        text: str,
        url: str | None = None,
        title: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> IndexResult:
        cleaned = (text or "").strip()
        if not cleaned:
            raise ValueError("text is required")
        key = (url or "").strip()
        doc_hash = hashlib.sha256(
            cleaned.encode("utf-8"), usedforsecurity=False
        ).hexdigest()
        storage_key = key or f"doc:{doc_hash}"
        resolved_title = (title or key or "Untitled").strip() or storage_key
        sim_signature = simhash64(cleaned)

        with start_span(
            "vector_index.upsert",
            attributes={"doc.length": len(cleaned)},
            inputs={"url": url, "metadata_keys": sorted(metadata.keys()) if metadata else []},
        ) as span:
            with self._lock:
                duplicate_key = self._simhash_index.nearest(sim_signature)
                if duplicate_key and duplicate_key != storage_key:
                    LOGGER.debug(
                        "dedupe skip for %s (duplicate of %s)", storage_key, duplicate_key
                    )
                    return IndexResult(
                        doc_id=storage_key,
                        chunks=0,
                        dims=self._last_dims,
                        duplicate_of=duplicate_key,
                    )
                needs_update = self._vector_store.needs_update(storage_key, None, doc_hash)
                if not needs_update:
                    self._simhash_index.update(storage_key, sim_signature)
                    self._persist_dedupe()
                    return IndexResult(doc_id=storage_key, chunks=0, dims=self._last_dims)

            chunks = self._chunker.chunk_text(cleaned)
            if not chunks:
                with self._lock:
                    self._simhash_index.update(storage_key, sim_signature)
                    self._persist_dedupe()
                return IndexResult(doc_id=storage_key, chunks=0, dims=self._last_dims)

            vectors = self._embed_documents([chunk.text for chunk in chunks])
            if len(vectors) != len(chunks):
                raise EmbedderUnavailableError(
                    self._embed_model,
                    detail="embedding count mismatch",
                )
            dims = len(vectors[0]) if vectors else 0

            with self._lock:
                self._vector_store.upsert(
                    storage_key,
                    resolved_title,
                    None,
                    doc_hash,
                    chunks,
                    vectors,
                    metadata=metadata,
                    doc_id=storage_key,
                )
                self._simhash_index.update(storage_key, sim_signature)
                self._persist_dedupe()
                if dims:
                    self._last_dims = dims
            LOGGER.info(
                "indexed document %s (title=%s, chunks=%s, dims=%s)",
                storage_key,
                resolved_title,
                len(chunks),
                dims,
            )
            if span is not None:
                span.set_attribute("vector.chunks", len(chunks))
                span.set_attribute("vector.dims", dims)
            return IndexResult(doc_id=storage_key, chunks=len(chunks), dims=dims)

    def search(
        self,
        query: str,
        *,
        k: int = 5,
        filters: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        cleaned = (query or "").strip()
        if not cleaned:
            return []
        with start_span(
            "vector_index.search",
            attributes={"search.k": k},
            inputs={"query": cleaned, "filters": filters},
        ) as span:
            vector = self._embed_query(cleaned)
            if not vector:
                return []
            sanitized_filters: dict[str, Any] | None = None
            if filters:
                sanitized_filters = {
                    str(key): value
                    for key, value in filters.items()
                    if value is not None
                }
                if not sanitized_filters:
                    sanitized_filters = None
            retrieved = self._vector_store.query(
                vector,
                max(1, int(k)),
                self._similarity_threshold,
                filters=sanitized_filters,
            )
            hits: list[SearchHit] = []
            for item in retrieved:
                hits.append(
                    SearchHit(
                        url=item.url,
                        title=item.title,
                        chunk=item.text,
                        score=float(item.similarity),
                    )
                )
            if span is not None:
                span.set_attribute("vector.results", len(hits))
            return [hit.to_dict() for hit in hits]

    def metadata(self) -> dict[str, Any]:
        dims = self._last_dims
        if dims == 0:
            dims = self._vector_store.embedding_dimensions()
            if dims:
                self._last_dims = dims
        return {
            "documents": self._vector_store.document_count(),
            "dimensions": dims,
            "model": self._embed_model,
            "test_mode": self._test_mode,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _persist_dedupe(self) -> None:
        try:
            self._simhash_index.save(self._dedupe_path)
        except Exception:  # pragma: no cover - persistence best effort
            LOGGER.debug("failed to persist vector simhash index", exc_info=True)

    def _ensure_embedder_ready(self) -> None:
        if self._test_mode:
            return
        assert self._embedder is not None  # noqa: S101 - programming error guard
        try:
            available = self._client.has_model(self._embed_model)
        except OllamaClientError as exc:
            raise EmbedderUnavailableError(self._embed_model, detail=str(exc)) from exc
        if available:
            return
        autopull_started = False
        if self._dev_allow_autopull and not self._autopull_started:
            try:
                ollama_services.pull_model(
                    self._embed_model, base_url=self._client.base_url
                )
            except FileNotFoundError as exc:
                LOGGER.warning("ollama CLI missing for autopull: %s", exc)
            except Exception as exc:  # pragma: no cover - subprocess edge cases
                LOGGER.warning(
                    "failed to start autopull for %s: %s", self._embed_model, exc
                )
            else:
                self._autopull_started = True
                autopull_started = True
                LOGGER.info(
                    "auto-pulling embedding model %s from %s",
                    self._embed_model,
                    self._client.base_url,
                )
        detail = (
            "embedding model is not available locally"
            if not self._dev_allow_autopull
            else "embedding model is warming up"
        )
        raise EmbedderUnavailableError(
            self._embed_model,
            detail=detail,
            autopull_started=autopull_started,
        )

    def _embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        if self._test_mode:
            return [
                _fallback_embed(text, dimensions=self._TEST_EMBED_DIMS)
                for text in texts
            ]
        self._ensure_embedder_ready()
        assert self._embedder is not None  # noqa: S101
        with start_span(
            "vector_index.embed_documents",
            attributes={"doc.count": len(texts)},
        ):
            try:
                vectors = self._embedder.embed_documents(texts)
            except EmbeddingError as exc:
                raise EmbedderUnavailableError(self._embed_model, detail=str(exc)) from exc
        if not vectors:
            raise EmbedderUnavailableError(
                self._embed_model,
                detail="embedding response was empty",
            )
        LOGGER.debug(
            "embedded %s chunks with %s",
            len(vectors),
            self._embed_model,
        )
        return vectors

    def _embed_query(self, query: str) -> list[float]:
        if self._test_mode:
            return _fallback_embed(query, dimensions=self._TEST_EMBED_DIMS)
        with start_span(
            "vector_index.embed_query",
            inputs={"query": query},
        ) as span:
            vectors = self._embed_documents([query])
            if span is not None and vectors:
                span.set_attribute("vector.dims", len(vectors[0]))
            return vectors[0] if vectors else []


__all__ = [
    "VectorIndexService",
    "EmbedderUnavailableError",
    "IndexResult",
    "SearchHit",
]
