"""Unit tests for the agent runtime fallback discovery heuristics."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.agent.document_store import DocumentStore, StoredDocument
from backend.agent.frontier_store import FrontierStore
from backend.agent.runtime import AgentRuntime, FetcherProtocol


class _VectorIndexStub:
    def search(self, *_args, **_kwargs):  # pragma: no cover - unused in these tests
        return []

    def metadata(self):  # pragma: no cover - unused in these tests
        return {}

    def upsert_document(self, **_kwargs):  # pragma: no cover - unused in these tests
        class _Result:
            chunks = 0

        return _Result()


class _FetcherStub(FetcherProtocol):
    def fetch(self, url: str):  # pragma: no cover - unused in these tests
        raise RuntimeError(f"unexpected fetch call for {url}")


@pytest.fixture
def runtime(tmp_path: Path) -> AgentRuntime:
    frontier = FrontierStore(tmp_path / "frontier.sqlite3")
    store = DocumentStore(tmp_path / "docs")
    vector_index = _VectorIndexStub()
    fetcher = _FetcherStub()
    return AgentRuntime(
        search_service=None,
        frontier=frontier,
        document_store=store,
        vector_index=vector_index,
        fetcher=fetcher,
    )


def test_candidate_urls_filters_invalid_hits(runtime: AgentRuntime) -> None:
    hits = [
        {"url": "https://example.com/path"},
        {"url": "HTTPS://EXAMPLE.com/path"},
        {"url": "ftp://example.com/resource"},
        {"url": "javascript:alert(1)"},
    ]

    candidates = runtime._candidate_urls("ignored", hits)

    assert candidates == ["https://example.com/path"]


def test_candidate_urls_fallback_runtime_sources(runtime: AgentRuntime, tmp_path: Path) -> None:
    doc = StoredDocument(
        url="https://docs.example.com/guide",
        title="Guide",
        text="Example body",
        sha256="abc123",
    )
    runtime.document_store.save(doc)

    candidates = runtime._candidate_urls("quantum computing", [])

    assert "https://docs.example.com/guide" in candidates

    from server.seeds_loader import load_seed_registry

    registry_urls = {
        url
        for entry in load_seed_registry()
        for url in entry.entrypoints
    }
    assert registry_urls.intersection(candidates)

    heuristic_expected = "https://en.wikipedia.org/wiki/Quantum_Computing"
    assert heuristic_expected in candidates


def test_candidate_urls_fallback_is_deterministic(runtime: AgentRuntime) -> None:
    first = runtime._candidate_urls("open source intelligence", [])
    second = runtime._candidate_urls("open source intelligence", [])
    assert first == second
