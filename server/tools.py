"""Tool adapters exposed to the planner agent."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any, Mapping, MutableMapping, Sequence

from backend.app.services.agent_browser import (
    AgentBrowserManager,
    BrowserActionError,
    BrowserSessionError,
    SessionNotFoundError,
)
from engine.data.store import RetrievedChunk, VectorStore
from engine.discovery.gather import gather_from_registry
from engine.indexing.chunk import TokenChunker
from engine.indexing.crawl import CrawlClient, CrawlError
from engine.indexing.embed import EmbeddingError, OllamaEmbedder

from server.tool_logging import log_tool

LOGGER = logging.getLogger(__name__)


class ToolExecutionError(RuntimeError):
    """Raised when a tool invocation cannot be completed."""


@dataclass(slots=True)
class IndexAPI:
    store: VectorStore
    embedder: OllamaEmbedder
    chunker: TokenChunker
    default_k: int = 5
    similarity_threshold: float = 0.2

    def search(
        self,
        *,
        query: str,
        k: int | None = None,
        threshold: float | None = None,
    ) -> MutableMapping[str, Any]:
        clean_query = (query or "").strip()
        if not clean_query:
            return {"query": clean_query, "results": []}
        limit = int(k) if k is not None else self.default_k
        limit = max(1, limit)
        try:
            embedding = self.embedder.embed_query(clean_query)
        except EmbeddingError as exc:
            raise ToolExecutionError(str(exc)) from exc
        use_threshold = threshold if threshold is not None else self.similarity_threshold
        hits = self.store.query(embedding, limit, use_threshold)
        results = [self._format_chunk(chunk) for chunk in hits]
        return {
            "query": clean_query,
            "results": results,
            "embedding_dimensions": len(embedding),
        }

    def upsert(
        self,
        *,
        url: str,
        text: str,
        title: str | None = None,
        etag: str | None = None,
        content_hash: str | None = None,
    ) -> MutableMapping[str, Any]:
        clean_url = (url or "").strip()
        if not clean_url:
            raise ToolExecutionError("url must be provided")
        body = (text or "").strip()
        if not body:
            raise ToolExecutionError("text must be provided")
        digest = content_hash or hashlib.sha256(body.encode("utf-8")).hexdigest()
        if not self.store.needs_update(clean_url, etag, digest):
            LOGGER.debug("index.upsert skipped %s (unchanged)", clean_url)
            return {"url": clean_url, "skipped": True}
        chunks = self.chunker.chunk_text(body)
        if not chunks:
            raise ToolExecutionError("unable to chunk document")
        try:
            embeddings = self.embedder.embed_documents([chunk.text for chunk in chunks])
        except EmbeddingError as exc:
            raise ToolExecutionError(str(exc)) from exc
        if len(embeddings) != len(chunks):
            raise ToolExecutionError("embedding count mismatch")
        self.store.upsert(
            url=clean_url,
            title=title or clean_url,
            etag=etag,
            content_hash=digest,
            chunks=chunks,
            embeddings=embeddings,
        )
        return {
            "url": clean_url,
            "chunks": len(chunks),
            "embedding_dimensions": len(embeddings[0]) if embeddings else 0,
            "skipped": False,
        }

    @staticmethod
    def _format_chunk(chunk: RetrievedChunk) -> dict[str, Any]:
        return {
            "text": chunk.text,
            "title": chunk.title,
            "url": chunk.url,
            "similarity": chunk.similarity,
        }


@dataclass(slots=True)
class CrawlerAPI:
    crawler: CrawlClient

    def fetch(self, *, url: str) -> MutableMapping[str, Any]:
        clean_url = (url or "").strip()
        if not clean_url:
            raise ToolExecutionError("url must be provided")
        try:
            result = self.crawler.fetch(clean_url)
        except CrawlError as exc:
            raise ToolExecutionError(str(exc)) from exc
        if result is None:
            raise ToolExecutionError("fetch returned no content")
        return {
            "url": result.url,
            "title": result.title,
            "text": result.text,
            "etag": result.etag,
            "content_hash": result.content_hash,
            "status_code": result.status_code,
        }

    def seeds_from_registry(
        self, *, query: str, limit: int | None = None
    ) -> MutableMapping[str, Any]:
        clean_query = (query or "").strip()
        if not clean_query:
            raise ToolExecutionError("query must be provided")
        cap = max(1, int(limit)) if limit is not None else 5
        candidates = gather_from_registry(clean_query, cap)
        return {
            "query": clean_query,
            "count": len(candidates),
            "candidates": [candidate.to_dict() for candidate in candidates],
        }


@dataclass(slots=True)
class EmbedAPI:
    embedder: OllamaEmbedder

    def embed_query(self, *, text: str) -> MutableMapping[str, Any]:
        body = (text or "").strip()
        if not body:
            raise ToolExecutionError("text must be provided")
        try:
            vector = self.embedder.embed_query(body)
        except EmbeddingError as exc:
            raise ToolExecutionError(str(exc)) from exc
        return {"embedding": vector, "dimensions": len(vector), "model": self.embedder.model}

    def embed_documents(self, *, texts: Sequence[str]) -> MutableMapping[str, Any]:
        sanitized = [str(text) for text in texts if str(text).strip()]
        if not sanitized:
            raise ToolExecutionError("texts must contain at least one entry")
        try:
            vectors = self.embedder.embed_documents(sanitized)
        except EmbeddingError as exc:
            raise ToolExecutionError(str(exc)) from exc
        return {
            "embeddings": vectors,
            "count": len(vectors),
            "model": self.embedder.model,
        }


@dataclass(slots=True)
class BrowserAPI:
    manager: AgentBrowserManager

    def _normalize_sid(self, sid: str) -> str:
        cleaned = (sid or "").strip()
        if not cleaned:
            raise ToolExecutionError("sid must be provided")
        return cleaned

    def navigate(self, *, sid: str, url: str) -> MutableMapping[str, Any]:
        clean_sid = self._normalize_sid(sid)
        clean_url = (url or "").strip()
        if not clean_url:
            raise ToolExecutionError("url must be provided")
        try:
            result = self.manager.navigate(clean_sid, clean_url)
        except SessionNotFoundError as exc:
            raise ToolExecutionError(str(exc)) from exc
        except BrowserActionError as exc:
            raise ToolExecutionError(str(exc)) from exc
        return {"sid": clean_sid, **result}

    def click(self, *, sid: str, selector: str) -> MutableMapping[str, Any]:
        clean_sid = self._normalize_sid(sid)
        clean_selector = (selector or "").strip()
        if not clean_selector:
            raise ToolExecutionError("selector must be provided")
        try:
            result = self.manager.click(clean_sid, clean_selector)
        except BrowserSessionError as exc:
            raise ToolExecutionError(str(exc)) from exc
        return {"sid": clean_sid, "selector": clean_selector, **result}

    def type(self, *, sid: str, selector: str, text: str) -> MutableMapping[str, Any]:
        clean_sid = self._normalize_sid(sid)
        clean_selector = (selector or "").strip()
        if not clean_selector:
            raise ToolExecutionError("selector must be provided")
        payload = text if isinstance(text, str) else str(text)
        try:
            result = self.manager.type(clean_sid, clean_selector, payload)
        except BrowserSessionError as exc:
            raise ToolExecutionError(str(exc)) from exc
        return {"sid": clean_sid, "selector": clean_selector, **result}

    def extract(self, *, sid: str) -> MutableMapping[str, Any]:
        clean_sid = self._normalize_sid(sid)
        try:
            result = self.manager.extract(clean_sid)
        except BrowserSessionError as exc:
            raise ToolExecutionError(str(exc)) from exc
        return {"sid": clean_sid, **result}


@dataclass
class ToolDispatcher:
    index_api: IndexAPI
    crawler_api: CrawlerAPI
    embed_api: EmbedAPI
    browser_api: BrowserAPI | None = None
    _registry: dict[str, Any] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._registry = {
            "index.search": log_tool("index.search")(self.index_api.search),
            "index.upsert": log_tool("index.upsert")(self.index_api.upsert),
            "crawl.fetch": log_tool("crawl.fetch")(self.crawler_api.fetch),
            "crawl.seeds": log_tool("crawl.seeds")(self.crawler_api.seeds_from_registry),
            "embed.query": log_tool("embed.query")(self.embed_api.embed_query),
            "embed.documents": log_tool("embed.documents")(self.embed_api.embed_documents),
        }
        self.attach_browser_api(self.browser_api)

    def attach_browser_api(self, api: BrowserAPI | None) -> None:
        self.browser_api = api
        for key in list(self._registry.keys()):
            if key.startswith("browser."):
                self._registry.pop(key, None)
        if api is None:
            return
        self._registry.update(
            {
                "browser.navigate": log_tool("browser.navigate")(api.navigate),
                "browser.click": log_tool("browser.click")(api.click),
                "browser.type": log_tool("browser.type")(api.type),
                "browser.extract": log_tool("browser.extract")(api.extract),
            }
        )

    def execute(self, tool: str, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
        handler = self._registry.get(tool)
        if handler is None:
            LOGGER.warning("planner requested unknown tool %s", tool)
            return {"ok": False, "tool": tool, "error": f"unknown tool: {tool}"}
        payload = params or {}
        try:
            result = handler(**{str(k): v for k, v in payload.items()})
        except ToolExecutionError as exc:
            LOGGER.info("tool %s failed: %s", tool, exc)
            return {"ok": False, "tool": tool, "error": str(exc)}
        except Exception as exc:  # pragma: no cover - defensive logging
            LOGGER.exception("unexpected error running tool %s", tool)
            return {"ok": False, "tool": tool, "error": str(exc)}
        return {"ok": True, "tool": tool, "result": result}

    def has_tool(self, name: str) -> bool:
        return name in self._registry

    def list_tools(self) -> Sequence[str]:
        return tuple(sorted(self._registry.keys()))


__all__ = [
    "ToolExecutionError",
    "IndexAPI",
    "CrawlerAPI",
    "EmbedAPI",
    "BrowserAPI",
    "ToolDispatcher",
]
