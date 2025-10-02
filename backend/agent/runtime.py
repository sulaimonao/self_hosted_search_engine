"""Agent runtime orchestrating retrieval, crawling, and indexing."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping, Sequence
from urllib.parse import quote_plus, urlparse

from backend.telemetry import event as telemetry_event
from backend.app.search.embedding import embed_query as _runtime_embed_query

from .document_store import DocumentStore, StoredDocument
from .frontier_store import FrontierStore
from backend.app.services.vector_index import (
    EmbedderUnavailableError,
    IndexResult,
    VectorIndexService,
)
from backend.retrieval.vector_store import LocalVectorStore, VectorDocument

LOGGER = logging.getLogger(__name__)

_ALLOWED_SCHEMES = {"http", "https"}


@dataclass(slots=True)
class FetchResult:
    url: str
    title: str
    text: str
    status_code: int
    sha256: str
    outlinks: Sequence[str] = field(default_factory=tuple)


class FetcherProtocol:
    """Protocol describing fetcher behavior (duck-typed)."""

    def fetch(self, url: str) -> FetchResult:  # pragma: no cover - structural typing only
        raise NotImplementedError


class SearchServiceProtocol:
    """Protocol for the BM25 search fallback."""

    def run_query(self, query: str, *, limit: int, use_llm: bool | None, model: str | None):  # pragma: no cover
        raise NotImplementedError


def _default_synthesizer(query: str, hits: Sequence[Mapping[str, object]]) -> tuple[str, list[str]]:
    citations = [str(hit.get("url")) for hit in hits[:3] if hit.get("url")]
    summary = "Found {} local results for '{}'.".format(len(hits), query)
    return summary, citations


class _VectorStoreAdapter:
    """Compatibility façade that mimics ``VectorIndexService`` over ``LocalVectorStore``."""

    def __init__(self, store: LocalVectorStore) -> None:
        self._store = store

    def search(self, query: str, *, k: int = 5, **_kwargs) -> list[dict[str, object]]:
        cleaned = (query or "").strip()
        if not cleaned:
            return []
        embeddings = embed_texts([cleaned])
        if not embeddings:
            return []
        embedding = embeddings[0]
        hits = self._store.query(embedding, k)
        payload: list[dict[str, object]] = []
        for hit in hits:
            payload.append(
                {
                    "url": hit.url,
                    "title": hit.title,
                    "chunk": hit.snippet,
                    "score": float(hit.score),
                }
            )
        return payload

    def upsert_document(
        self,
        *,
        text: str,
        url: str | None = None,
        title: str | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> IndexResult:
        cleaned = (text or "").strip()
        if not cleaned:
            raise ValueError("text is required")
        doc_id = (url or "").strip()
        if not doc_id and metadata:
            sha = str(metadata.get("sha256", "")).strip()
            if sha:
                doc_id = sha
        if not doc_id:
            doc_id = hashlib.sha256(cleaned.encode("utf-8"), usedforsecurity=False).hexdigest()
        embeddings = embed_texts([cleaned])
        if not embeddings:
            return IndexResult(doc_id=doc_id, chunks=0, dims=0)
        embedding = embeddings[0]
        document = VectorDocument(
            doc_id=doc_id,
            url=url or "",
            title=(title or url or "Untitled").strip() or doc_id,
            text=cleaned,
            embedding=embedding,
        )
        changed, _skipped = self._store.upsert_many([document])
        chunks = int(bool(changed))
        dims = len(embedding)
        return IndexResult(doc_id=doc_id, chunks=chunks, dims=dims)

    def metadata(self) -> Mapping[str, object]:
        return self._store.to_metadata()


@dataclass
class AgentRuntime:
    """Coordinate the agent's tool execution."""

    search_service: SearchServiceProtocol | None
    frontier: FrontierStore
    document_store: DocumentStore
    fetcher: FetcherProtocol
    vector_index: VectorIndexService | _VectorStoreAdapter | None = None
    vector_store: LocalVectorStore | None = None
    max_fetch_per_turn: int = 3
    coverage_threshold: float = 0.6
    synthesizer: Callable[[str, Sequence[Mapping[str, object]]], tuple[str, list[str]]] = _default_synthesizer

    def __post_init__(self) -> None:
        if self.vector_index is None:
            if self.vector_store is None:
                raise ValueError("AgentRuntime requires either vector_index or vector_store")
            self.vector_index = _VectorStoreAdapter(self.vector_store)
        elif self.vector_store is None:
            self.vector_store = getattr(self.vector_index, "vector_store", None)

    def search_index(self, query: str, *, k: int = 20, use_embeddings: bool = True) -> list[dict[str, object]]:
        clean_query = (query or "").strip()
        if not clean_query:
            return []
        combined: dict[str, dict[str, object]] = {}
        if use_embeddings:
            try:
                vector_hits = self.vector_index.search(clean_query, k=k)
            except EmbedderUnavailableError:
                LOGGER.debug("Embedding unavailable; falling back to BM25 only", exc_info=True)
                vector_hits = []
            for rank, hit in enumerate(vector_hits, start=1):
                url = str(hit.get("url", ""))
                if not url:
                    continue
                combined.setdefault(
                    url,
                    {
                        "url": url,
                        "title": hit.get("title"),
                        "snippet": hit.get("chunk"),
                        "score": float(hit.get("score", 0.0)),
                        "source": "vector",
                        "rank": rank,
                    },
                )
        if self.search_service:
            results, _job, _context = self.search_service.run_query(
                clean_query, limit=max(5, k), use_llm=False, model=None
            )
            for rank, item in enumerate(results, start=1):
                url = str(item.get("url", ""))
                if not url:
                    continue
                entry = combined.setdefault(url, {
                    "url": url,
                    "title": item.get("title"),
                    "snippet": item.get("snippet"),
                    "score": float(item.get("score", 0.0)),
                    "source": "bm25",
                    "rank": rank,
                })
                if entry["source"] == "vector":
                    entry.setdefault("bm25_rank", rank)
                    entry.setdefault("snippet", item.get("snippet"))
        ordered = sorted(combined.values(), key=lambda hit: hit.get("rank", 9999))
        return ordered[:k]

    def enqueue_crawl(
        self,
        url: str,
        *,
        priority: float = 0.5,
        topic: str | None = None,
        reason: str | None = None,
        source_task_id: str | None = None,
    ) -> bool:
        enqueued = self.frontier.enqueue(
            url,
            priority=priority,
            topic=topic,
            reason=reason,
            source_task_id=source_task_id,
        )
        telemetry_event("agent.enqueue", {"url": url, "priority": priority, "topic": topic, "reason": reason})
        return enqueued

    def fetch_page(self, url: str) -> dict[str, object]:
        result = self.fetcher.fetch(url)
        if not result.text.strip():
            return {"url": url, "status": "skipped"}
        document = StoredDocument(
            url=result.url,
            title=result.title or result.url,
            text=result.text,
            sha256=result.sha256,
        )
        path = self.document_store.save(document)
        telemetry_event("agent.fetch", {"url": url, "status_code": result.status_code, "path": str(path)})
        return {
            "url": result.url,
            "title": result.title,
            "status": result.status_code,
            "sha256": result.sha256,
            "outlinks": list(result.outlinks),
        }

    def reindex(self, urls: Sequence[str] | None = None) -> dict[str, int]:
        documents = list(self.document_store.iter_documents(urls))
        if not documents:
            return {"changed": 0, "skipped": 0}
        changed = 0
        skipped = 0
        for doc in documents:
            try:
                result = self.vector_index.upsert_document(
                    text=doc.text,
                    url=doc.url,
                    title=doc.title,
                    metadata={"sha256": doc.sha256},
                )
            except EmbedderUnavailableError:
                LOGGER.warning(
                    "Embeddings unavailable for reindex; skipping remaining docs",
                    exc_info=True,
                )
                remaining = len(documents) - (changed + skipped)
                return {"changed": changed, "skipped": skipped + remaining}
            if result.chunks > 0:
                changed += 1
            else:
                skipped += 1
        telemetry_event("agent.reindex", {"changed": changed, "skipped": skipped})
        return {"changed": changed, "skipped": skipped}

    def status(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "frontier": self.frontier.to_dict(),
            "vector_store": self.vector_index.metadata(),
        }
        return payload

    def coverage_score(self, hits: Sequence[Mapping[str, object]]) -> float:
        if not hits:
            return 0.0
        return min(1.0, len(hits) / 10.0)

    def handle_turn(self, query: str) -> dict[str, object]:
        hits = self.search_index(query, k=20, use_embeddings=True)
        coverage = self.coverage_score(hits)
        actions: list[dict[str, object]] = [
            {"search": {"results": len(hits), "coverage": coverage}}
        ]
        queued_urls: list[str] = []
        fetched: list[dict[str, object]] = []
        if coverage < self.coverage_threshold:
            candidates = self._candidate_urls(query, hits)
            for candidate in candidates:
                if self.enqueue_crawl(candidate, topic=query, reason="low_coverage"):
                    queued_urls.append(candidate)
            for candidate in candidates[: self.max_fetch_per_turn]:
                fetch_result = self.fetch_page(candidate)
                fetched.append(fetch_result)
            if fetched:
                reindex_result = self.reindex([item["url"] for item in fetched if item.get("status")])
                actions.append({"reindex": reindex_result})
        if queued_urls:
            actions.append({"queued": len(queued_urls)})
        if fetched:
            actions.append({"fetched": [{"url": item["url"], "status": item.get("status")} for item in fetched]})
        answer, citations = self.synthesizer(query, hits)
        return {
            "answer": answer,
            "citations": citations,
            "coverage": coverage,
            "actions": actions,
            "results": hits,
        }

    def _candidate_urls(self, query: str, hits: Sequence[Mapping[str, object]]) -> list[str]:
        """Return crawl targets ranked by existing evidence and fallbacks."""

        candidates: list[str] = []
        seen: set[str] = set()

        def _record(url: str) -> None:
            normalized = self._normalize_candidate_url(url)
            if not normalized or normalized in seen:
                return
            seen.add(normalized)
            candidates.append(normalized)

        for hit in hits:
            raw_url = hit.get("url")
            if raw_url:
                _record(str(raw_url))

        if candidates:
            return candidates

        for url in self._recent_discovery_urls(limit=5):
            _record(url)

        for url in self._registry_suggestions(query, limit=10):
            _record(url)

        for url in self._heuristic_candidates(query):
            _record(url)

        return candidates

    def _normalize_candidate_url(self, url: str) -> str | None:
        candidate = (url or "").strip()
        if not candidate:
            return None

        parsed = urlparse(candidate)
        if not parsed.scheme:
            parsed = urlparse(f"https://{candidate.lstrip('/')}")
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()
        if scheme not in _ALLOWED_SCHEMES or not netloc:
            return None

        sanitized_path = parsed.path or "/"
        sanitized = f"{scheme}://{netloc}{sanitized_path}"
        if parsed.query:
            sanitized = f"{sanitized}?{parsed.query}"
        return sanitized.rstrip("/")

    def _recent_discovery_urls(self, *, limit: int) -> list[str]:
        root = getattr(self.document_store, "root", None)
        if not isinstance(root, Path):
            return []
        try:
            paths = sorted(root.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
        except OSError:
            return []

        urls: list[str] = []
        for path in paths[:limit]:
            try:
                payload = json.loads(path.read_text("utf-8"))
            except (OSError, ValueError):
                continue
            url = payload.get("url")
            if isinstance(url, str) and url:
                urls.append(url)
        return urls

    def _registry_suggestions(self, query: str, *, limit: int) -> list[str]:
        try:
            from server.seeds_loader import load_seed_registry
        except Exception:  # pragma: no cover - import error path is rare
            LOGGER.debug("failed to load seed registry", exc_info=True)
            return []

        entries = load_seed_registry()
        if not entries:
            return []

        tokens = self._tokenize(query)
        token_set = set(tokens)
        scored: list[tuple[float, str]] = []
        for entry in entries:
            extras = entry.extras
            tags = {str(tag).lower() for tag in extras.get("tags", []) if isinstance(tag, str)}
            descriptor_parts = [
                entry.id,
                entry.kind,
                entry.strategy,
                *(extras.get(key, "") for key in ("title", "collection", "notes")),
                " ".join(sorted(tags)),
            ]
            descriptor = " ".join(part.lower() for part in descriptor_parts if part)
            match_count = sum(1 for token in token_set if token in descriptor or token in tags)
            trust_score = self._trust_score(entry.trust)
            strategy_bonus = 0.2 if entry.strategy in {"feed", "portal", "docs"} else 0.0
            wikipedia_bonus = 0.3 if "wikipedia" in entry.id else 0.0
            score = 1.0 + trust_score + strategy_bonus + wikipedia_bonus + match_count * 0.75
            for url in entry.entrypoints:
                scored.append((score, url))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [url for _, url in scored[:limit]]

    def _heuristic_candidates(self, query: str) -> list[str]:
        tokens = self._tokenize(query)
        if not tokens:
            return []

        slug = "_".join(token.capitalize() for token in tokens)
        encoded = quote_plus(query.strip())
        heuristics = [
            f"https://en.wikipedia.org/wiki/{slug}",
            f"https://news.google.com/search?q={encoded}",
            f"https://www.britannica.com/search?query={encoded}",
        ]
        return heuristics

    @staticmethod
    def _tokenize(text: str) -> tuple[str, ...]:
        if not text:
            return tuple()
        ordered: list[str] = []
        seen: set[str] = set()
        for token in re.findall(r"[a-z0-9]+", text.lower()):
            if token in seen:
                continue
            ordered.append(token)
            seen.add(token)
        return tuple(ordered)

    @staticmethod
    def _trust_score(value: object) -> float:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered == "high":
                return 1.0
            if lowered == "medium":
                return 0.5
            if lowered == "low":
                return 0.1
            try:
                return float(lowered)
            except ValueError:
                return 0.0
        return 0.0


class CrawlFetcher(FetcherProtocol):
    """Adapter turning CrawlClient into the fetcher protocol."""

    def __init__(self, crawler) -> None:  # pragma: no cover - thin wrapper
        self._crawler = crawler

    def fetch(self, url: str) -> FetchResult:
        result = self._crawler.fetch(url)
        if result is None:
            return FetchResult(url=url, title=url, text="", status_code=0, sha256="")
        outlinks: list[str] = []
        sha = result.content_hash or hashlib.sha256(result.text.encode("utf-8")).hexdigest()
        return FetchResult(
            url=result.url,
            title=result.title or result.url,
            text=result.text,
            status_code=result.status_code,
            sha256=sha,
            outlinks=tuple(outlinks),
        )


__all__ = ["AgentRuntime", "CrawlFetcher", "FetchResult"]


def embed_texts(texts: Sequence[str]) -> list[list[float]]:
    """Embed a batch of texts using the deterministic fallback."""

    return [_runtime_embed_query(text) for text in texts]

