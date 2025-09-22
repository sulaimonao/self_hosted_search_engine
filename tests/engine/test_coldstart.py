from crawler.frontier import Candidate

from engine.indexing.coldstart import ColdStartIndexer
from engine.indexing.crawl import CrawlResult
from engine.indexing.chunk import Chunk


class StubStore:
    def __init__(self) -> None:
        self.upserts: list[str] = []

    def needs_update(self, url: str, etag: str | None, content_hash: str) -> bool:
        return True

    def upsert(self, url: str, title: str, etag: str | None, content_hash: str, chunks, embeddings) -> None:  # noqa: D401
        self.upserts.append(url)


class StubCrawler:
    def __init__(self) -> None:
        self.visited: list[str] = []
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


class StubLearnedDB:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def record_discovery(self, query: str, url: str, *, reason: str, score: float, source=None, **kwargs):  # noqa: D401
        self.records.append(
            {
                "query": query,
                "url": url,
                "reason": reason,
                "score": score,
                "source": source,
            }
        )
        return 1, True


def test_build_index_uses_candidate_provider_and_records_discoveries():
    store = StubStore()
    crawler = StubCrawler()
    chunker = StubChunker()
    embedder = StubEmbedder()
    learned_db = StubLearnedDB()

    captured: dict[str, tuple] = {}

    def candidate_provider(query: str, limit: int, use_llm: bool, model: str | None):
        captured["args"] = (query, limit, use_llm, model)
        return [
            Candidate(url="https://alpha.example/docs", source="registry", weight=1.5, score=1.5),
            Candidate(url="https://beta.example/blog", source="learned", weight=0.9, score=0.9),
        ]

    indexer = ColdStartIndexer(
        store=store,
        crawler=crawler,
        chunker=chunker,
        embedder=embedder,
        learned_db=learned_db,
        candidate_provider=candidate_provider,
        llm_seed_provider=None,
        max_pages=2,
    )

    indexed = indexer.build_index("sample query", use_llm=True, llm_model="ollama")

    assert indexed == 2
    assert crawler.visited == [
        "https://alpha.example/docs",
        "https://beta.example/blog",
    ]
    assert store.upserts == crawler.visited
    assert captured["args"] == ("sample query", 2, True, "ollama")
    assert [record["url"] for record in learned_db.records] == crawler.visited
    assert all(record["reason"].startswith("coldstart:") for record in learned_db.records)


def test_default_discovery_helper_calls_discover_and_registry():
    store = StubStore()
    crawler = StubCrawler()
    chunker = StubChunker()
    embedder = StubEmbedder()
    learned_db = StubLearnedDB()

    class FakeEngine:
        def __init__(self) -> None:
            self.calls: list[tuple] = []

        def discover(self, query, *, limit, extra_seeds, use_llm, model):
            self.calls.append(("discover", query, limit, tuple(extra_seeds), use_llm, model))
            return []

        def registry_frontier(self, query, *, limit, use_llm, model):
            self.calls.append(("registry", query, limit, use_llm, model))
            return [
                Candidate(
                    url="https://docs.gamma.dev",
                    source="registry",
                    weight=1.0,
                    score=1.2,
                )
            ]

    engine = FakeEngine()
    llm_calls: dict[str, tuple] = {}

    def llm_seed_provider(query: str, limit: int, model: str | None):
        llm_calls["args"] = (query, limit, model)
        return ["https://planner.example/path", "https://planner.example/path"]

    indexer = ColdStartIndexer(
        store=store,
        crawler=crawler,
        chunker=chunker,
        embedder=embedder,
        discovery_engine=engine,
        learned_db=learned_db,
        llm_seed_provider=llm_seed_provider,
        max_pages=1,
    )

    indexed = indexer.build_index("gamma docs", use_llm=True, llm_model="llama")

    assert indexed == 1
    assert crawler.visited == ["https://docs.gamma.dev"]
    assert store.upserts == ["https://docs.gamma.dev"]
    assert llm_calls["args"] == ("gamma docs", 1, "llama")
    assert engine.calls[0] == (
        "discover",
        "gamma docs",
        1,
        ("https://planner.example/path",),
        True,
        "llama",
    )
    assert engine.calls[1][0] == "registry"
    assert learned_db.records and learned_db.records[0]["url"] == "https://docs.gamma.dev"
    assert learned_db.records[0]["reason"] == "coldstart:registry"
