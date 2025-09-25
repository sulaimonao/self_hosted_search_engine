from __future__ import annotations

import hashlib

import pytest

from backend.agent.document_store import DocumentStore, StoredDocument
from backend.agent.frontier_store import FrontierStore
from backend.agent.runtime import AgentRuntime, FetchResult
from backend.retrieval.vector_store import LocalVectorStore


class _StubFetcher:
    def fetch(self, url: str) -> FetchResult:  # pragma: no cover - not exercised here
        raise RuntimeError("should not be called")


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    frontier = FrontierStore(tmp_path / "frontier.sqlite3")
    documents = DocumentStore(tmp_path / "docs")
    vector_store = LocalVectorStore(tmp_path / "vectors")
    monkeypatch.setattr(
        "backend.agent.runtime.embed_texts",
        lambda texts: [[float(len(texts[i])), float(len(texts[i]))] for i in range(len(texts))],
    )
    return AgentRuntime(
        search_service=None,
        frontier=frontier,
        document_store=documents,
        vector_store=vector_store,
        fetcher=_StubFetcher(),
    )


def test_reindex_updates_vector_store(runtime: AgentRuntime):
    doc = StoredDocument(
        url="https://example.com/page",
        title="Example",
        text="content body",
        sha256=hashlib.sha256(b"content body").hexdigest(),
    )
    runtime.document_store.save(doc)
    result = runtime.reindex([doc.url])
    assert result == {"changed": 1, "skipped": 0}
    metadata = runtime.vector_store.to_metadata()
    assert metadata["documents"] == 1
    assert metadata["dimensions"] == 2
