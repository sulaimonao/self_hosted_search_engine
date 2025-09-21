"""Cold-start orchestration for building the knowledge base."""

from __future__ import annotations

from typing import Callable, Sequence

from ..data.store import VectorStore
from ..search.provider import seed_urls_for_query
from .chunk import TokenChunker
from .crawl import CrawlClient, CrawlError
from .embed import OllamaEmbedder

SeedProvider = Callable[[str, int], Sequence[str]]
LLMSeedProvider = Callable[[str, int, str | None], Sequence[str]]


class ColdStartIndexer:
    """Coordinates crawl, chunk, embed, store pipeline when data is missing."""

    def __init__(
        self,
        store: VectorStore,
        crawler: CrawlClient,
        chunker: TokenChunker,
        embedder: OllamaEmbedder,
        seed_provider: SeedProvider = seed_urls_for_query,
        llm_seed_provider: LLMSeedProvider | None = None,
        max_pages: int = 5,
    ) -> None:
        self._store = store
        self._crawler = crawler
        self._chunker = chunker
        self._embedder = embedder
        self._seed_provider = seed_provider
        self._llm_seed_provider = llm_seed_provider
        self._max_pages = max_pages

    def build_index(
        self, query: str, *, use_llm: bool = False, llm_model: str | None = None
    ) -> int:
        base_urls = list(self._seed_provider(query, self._max_pages) or [])
        llm_urls: list[str] = []
        if use_llm and self._llm_seed_provider is not None:
            llm_urls = [
                url
                for url in self._llm_seed_provider(query, self._max_pages, llm_model)
                if isinstance(url, str) and url
            ]
        combined: list[str] = []
        for url in llm_urls + base_urls:
            if url and url not in combined:
                combined.append(url)
        urls = combined or base_urls
        indexed = 0
        for url in urls:
            if indexed >= self._max_pages:
                break
            try:
                result = self._crawler.fetch(url)
            except CrawlError:
                continue
            if result is None:
                continue
            if not self._store.needs_update(url, result.etag, result.content_hash):
                continue
            chunks = self._chunker.chunk_text(result.text)
            if not chunks:
                continue
            embeddings = self._embedder.embed_documents([chunk.text for chunk in chunks])
            if not embeddings:
                continue
            self._store.upsert(
                url=url,
                title=result.title,
                etag=result.etag,
                content_hash=result.content_hash,
                chunks=chunks,
                embeddings=embeddings,
            )
            indexed += 1
        return indexed


__all__ = ["ColdStartIndexer"]
