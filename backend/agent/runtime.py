"""Agent runtime orchestrating retrieval, crawling, and indexing."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Callable, Mapping, Sequence

from backend.telemetry import event as telemetry_event

from .document_store import DocumentStore, StoredDocument
from .frontier_store import FrontierStore
from backend.app.services.vector_index import (
    EmbedderUnavailableError,
    VectorIndexService,
)

LOGGER = logging.getLogger(__name__)


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


@dataclass
class AgentRuntime:
    """Coordinate the agent's tool execution."""

    search_service: SearchServiceProtocol | None
    frontier: FrontierStore
    document_store: DocumentStore
    vector_index: VectorIndexService
    fetcher: FetcherProtocol
    max_fetch_per_turn: int = 3
    coverage_threshold: float = 0.6
    synthesizer: Callable[[str, Sequence[Mapping[str, object]]], tuple[str, list[str]]] = _default_synthesizer

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
        seeds: list[str] = []
        for hit in hits:
            url = str(hit.get("url", ""))
            if url:
                seeds.append(url)
        if not seeds:
            digest = hashlib.sha1(query.encode("utf-8")).hexdigest()[:16]
            seeds.append(f"https://example.com/research/{digest}")
        seen: set[str] = set()
        unique: list[str] = []
        for url in seeds:
            if url not in seen:
                seen.add(url)
                unique.append(url)
        return unique


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
