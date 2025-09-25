from __future__ import annotations

import hashlib

from backend.agent.document_store import DocumentStore
from backend.agent.frontier_store import FrontierStore
from backend.agent.runtime import AgentRuntime, FetchResult
from backend.retrieval.vector_store import LocalVectorStore


class _StubFetcher:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def fetch(self, url: str) -> FetchResult:
        self.calls.append(url)
        text = f"Deep dive content for {url}"
        sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return FetchResult(url=url, title=f"Doc for {url}", text=text, status_code=200, sha256=sha, outlinks=())


class _StubSearch:
    def run_query(self, query: str, *, limit: int, use_llm, model):
        return ([], None, {})


def test_agent_increases_coverage(monkeypatch, tmp_path):
    frontier = FrontierStore(tmp_path / "frontier.sqlite3")
    documents = DocumentStore(tmp_path / "docs")
    vector_store = LocalVectorStore(tmp_path / "vectors")
    fetcher = _StubFetcher()

    def _fake_embed_texts(texts):
        vectors = []
        for text in texts:
            length = float(len(text)) or 1.0
            vectors.append([length, length / 2])
        return vectors

    monkeypatch.setattr("backend.agent.runtime.embed_texts", _fake_embed_texts)

    runtime = AgentRuntime(
        search_service=_StubSearch(),
        frontier=frontier,
        document_store=documents,
        vector_store=vector_store,
        fetcher=fetcher,
        max_fetch_per_turn=2,
        coverage_threshold=0.6,
    )

    first = runtime.handle_turn("new framework tutorials")
    assert first["coverage"] < 0.6
    assert any(action.get("queued") for action in first["actions"] if isinstance(action, dict))
    assert fetcher.calls, "agent should fetch pages when coverage is low"

    second = runtime.handle_turn("new framework tutorials")
    assert second["coverage"] > first["coverage"]
    assert second["results"], "second turn should surface indexed hits"
    assert second["citations"], "answer should include citations"
