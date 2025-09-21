from __future__ import annotations

from typing import List

from engine.indexing.coldstart import ColdStartIndexer
from engine.indexing.crawl import CrawlResult
from engine.indexing.chunk import Chunk


class StubStore:
    def __init__(self) -> None:
        self.upserts: List[str] = []

    def needs_update(self, url: str, etag: str | None, content_hash: str) -> bool:
        return True

    def upsert(self, url: str, title: str, etag: str | None, content_hash: str, chunks, embeddings) -> None:  # noqa: D401
        self.upserts.append(url)


class StubCrawler:
    def __init__(self) -> None:
        self.visited: List[str] = []
        self.counter = 0

    def fetch(self, url: str) -> CrawlResult | None:
        self.visited.append(url)
        self.counter += 1
        return CrawlResult(
            url=url,
            status_code=200,
            html="<html></html>",
            text=f"Document body for {url}",
            title=f"Title {self.counter}",
            etag=None,
            last_modified=None,
            content_hash=f"hash-{self.counter}",
        )


class StubChunker:
    def chunk_text(self, text: str):
        return [Chunk(text=text, start=0, end=len(text), token_count=1)]


class StubEmbedder:
    def embed_documents(self, texts):
        return [[0.1] * 1 for _ in texts]


def test_build_index_uses_llm_seeds_when_enabled():
    store = StubStore()
    crawler = StubCrawler()
    chunker = StubChunker()
    embedder = StubEmbedder()

    def base_seeds(query: str, limit: int):
        return ["https://base.example"]

    captured = {}

    def llm_seeds(query: str, limit: int, model: str | None):
        captured["args"] = (query, limit, model)
        return ["https://llm.example", "https://base.example"]

    indexer = ColdStartIndexer(
        store=store,
        crawler=crawler,
        chunker=chunker,
        embedder=embedder,
        seed_provider=base_seeds,
        llm_seed_provider=llm_seeds,
        max_pages=2,
    )

    indexed = indexer.build_index("sample query", use_llm=True, llm_model="my-llm")

    assert indexed == 2
    assert crawler.visited == ["https://llm.example", "https://base.example"]
    assert captured["args"] == ("sample query", 2, "my-llm")


def test_build_index_skips_llm_when_disabled():
    store = StubStore()
    crawler = StubCrawler()
    chunker = StubChunker()
    embedder = StubEmbedder()

    def base_seeds(query: str, limit: int):
        return ["https://base-only.example"]

    llm_calls: List[tuple] = []

    def llm_seeds(query: str, limit: int, model: str | None):
        llm_calls.append((query, limit, model))
        return ["https://llm.example"]

    indexer = ColdStartIndexer(
        store=store,
        crawler=crawler,
        chunker=chunker,
        embedder=embedder,
        seed_provider=base_seeds,
        llm_seed_provider=llm_seeds,
        max_pages=1,
    )

    indexed = indexer.build_index("another query", use_llm=False, llm_model="ignored")

    assert indexed == 1
    assert crawler.visited == ["https://base-only.example"]
    assert llm_calls == []
