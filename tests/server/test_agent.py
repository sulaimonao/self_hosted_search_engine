"""Tests for the planner agent stack (LLM wrapper + tool dispatcher)."""

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from engine.discovery.gather import RegistryCandidate
from engine.data.store import RetrievedChunk
from engine.indexing.chunk import TokenChunker
from engine.indexing.crawl import CrawlResult, CrawlError

from server.agent import PlannerAgent
from server.llm import OllamaJSONClient
from server.tools import CrawlerAPI, EmbedAPI, IndexAPI, ToolDispatcher


class FakeResponse:
    def __init__(self, payload, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError("boom")

    def json(self):  # pragma: no cover - trivial
        return self._payload


class FakeSession:
    def __init__(self, post_payload):
        self.post_payload = post_payload
        self.post_calls = []

    def get(self, url, timeout):  # pragma: no cover - defensive
        return FakeResponse({"models": [{"name": "llama"}]})

    def post(self, url, json, timeout):
        self.post_calls.append((url, json))
        return FakeResponse(self.post_payload)


def test_json_client_parses_code_fence():
    payload = {
        "message": {
            "content": "```json\n{\"type\":\"final\",\"answer\":\"ok\",\"sources\":[]}\n```"
        }
    }
    client = OllamaJSONClient(base_url="http://fake", default_model="llama", session=FakeSession(payload))
    result = client.chat_json([{"role": "user", "content": "hi"}])
    assert result["type"] == "final"
    assert result["answer"] == "ok"


def test_json_client_accepts_object_payload():
    payload = {
        "message": {
            "content": {
                "type": "final",
                "answer": "structured",
                "sources": ["https://example"],
            }
        }
    }
    client = OllamaJSONClient(base_url="http://fake", default_model="llama", session=FakeSession(payload))
    result = client.chat_json([{"role": "user", "content": "hi"}])
    assert result["type"] == "final"
    assert result["answer"] == "structured"
    assert result["sources"] == ["https://example"]


class FakeVectorStore:
    def __init__(self):
        self.upserts = []
        self.checked = []

    def query(self, vector, k, threshold):
        return [RetrievedChunk(text="chunk", title="Doc", url="https://example", similarity=0.9)]

    def needs_update(self, url, etag, content_hash):
        self.checked.append((url, content_hash))
        return True

    def upsert(self, url, title, etag, content_hash, chunks, embeddings):
        self.upserts.append((url, title, etag, content_hash, chunks, embeddings))


class FakeEmbedder:
    model = "fake-embed"

    def embed_query(self, text: str):
        return [1.0, 0.0, 0.5]

    def embed_documents(self, texts):
        return [[float(index + 1)] for index, _ in enumerate(texts)]


@dataclass
class FakeCrawler:
    def fetch(self, url: str):
        if url == "fail":
            raise CrawlError("boom")
        if url == "empty":
            return None
        return CrawlResult(
            url=url,
            status_code=200,
            html="<html></html>",
            text="hello world",
            title="Example",
            etag="etag",
            last_modified=None,
            content_hash="hash",
        )


@pytest.fixture()
def dispatcher(monkeypatch):
    vector_store = FakeVectorStore()
    embedder = FakeEmbedder()
    chunker = TokenChunker(chunk_size=20, overlap=0)
    index_api = IndexAPI(vector_store, embedder, chunker, default_k=3, similarity_threshold=0.2)
    crawler_api = CrawlerAPI(FakeCrawler())
    embed_api = EmbedAPI(embedder)
    monkeypatch.setattr("server.tools.gather_from_registry", lambda query, max_candidates: [])
    return ToolDispatcher(index_api=index_api, crawler_api=crawler_api, embed_api=embed_api)


def test_tool_dispatcher_handles_success_and_failure(dispatcher):
    search = dispatcher.execute("index.search", {"query": "hello"})
    assert search["ok"]
    assert search["result"]["results"]

    upsert = dispatcher.execute("index.upsert", {"url": "https://example", "text": "hello world"})
    assert upsert["ok"]
    assert upsert["result"]["chunks"] == 1

    failure = dispatcher.execute("crawl.fetch", {"url": "empty"})
    assert not failure["ok"]
    assert "error" in failure


def test_crawl_seeds_tool(dispatcher, monkeypatch):
    sample = [
        RegistryCandidate(
            url="https://example.com",
            score=1.5,
            source="registry:test",
            strategy="rss_hub",
            entry_id="test",
            metadata={"feed": "https://feed"},
        )
    ]
    monkeypatch.setattr("server.tools.gather_from_registry", lambda query, max_candidates: sample)
    result = dispatcher.execute("crawl.seeds", {"query": "widgets", "limit": 3})
    assert result["ok"]
    payload = result["result"]
    assert payload["query"] == "widgets"
    assert payload["count"] == 1
    assert payload["candidates"][0]["url"] == "https://example.com"


class FakeLLM:
    def __init__(self):
        self.calls = 0

    def chat_json(self, messages, model=None):
        self.calls += 1
        if self.calls == 1:
            return {"type": "tool", "tool": "index.search", "params": {"query": "widgets"}}
        tool_messages = [m for m in messages if m.get("role") == "tool"]
        assert tool_messages, "tool result should be returned to the model"
        return {"type": "final", "answer": "done", "sources": ["https://example"]}


def test_planner_agent_runs_tool_loop(dispatcher):
    agent = PlannerAgent(
        llm=FakeLLM(),
        tools=dispatcher,
        max_iterations=3,
        enable_critique=False,
    )
    final = agent.run("Find widgets")
    assert final["type"] == "final"
    assert final["answer"] == "done"
    assert final["steps"]
    assert final.get("stop_reason") == "finalized"


class LoopLLM:
    def chat_json(self, messages, model=None):
        return {"type": "tool", "tool": "index.search", "params": {"query": "loop"}}


def test_planner_agent_enforces_iteration_limit(dispatcher):
    agent = PlannerAgent(
        llm=LoopLLM(),
        tools=dispatcher,
        max_iterations=2,
        enable_critique=False,
    )
    final = agent.run("Loop forever")
    assert final["type"] == "final"
    assert final.get("error") == "iteration limit reached"
    assert len(final["steps"]) == 2
    assert final.get("stop_reason") == "max_steps"
