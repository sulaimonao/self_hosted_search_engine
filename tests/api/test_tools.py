from __future__ import annotations

from flask import Flask

from backend.app.api import agent_tools


class StubRuntime:
    def __init__(self) -> None:
        self.enqueued: list[dict] = []
        self.fetched: list[str] = []

    def search_index(self, query: str, *, k: int, use_embeddings: bool):
        return [
            {"url": "https://example.com", "title": "Example", "snippet": "snippet", "score": 1.0}
        ]

    def enqueue_crawl(self, url: str, *, priority: float, topic: str | None, reason: str | None, source_task_id=None):
        self.enqueued.append({"url": url, "priority": priority, "topic": topic, "reason": reason})
        return True

    def fetch_page(self, url: str):
        self.fetched.append(url)
        return {"url": url, "title": "Fetched", "status": 200, "sha256": "abc", "outlinks": []}

    def reindex(self, urls):
        return {"changed": len(urls or []), "skipped": 0}

    def status(self):
        return {"frontier": {"queued": len(self.enqueued)}, "vector_store": {"documents": 0}}

    def handle_turn(self, query: str):
        return {"answer": "ok", "citations": ["https://example.com"], "coverage": 1.0, "actions": [], "results": []}


def _app(runtime: StubRuntime) -> Flask:
    app = Flask(__name__)
    app.register_blueprint(agent_tools.bp)
    app.config["AGENT_RUNTIME"] = runtime
    return app


def test_search_endpoint():
    runtime = StubRuntime()
    client = _app(runtime).test_client()
    response = client.post("/api/tools/search_index", json={"query": "test"})
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["results"][0]["url"] == "https://example.com"


def test_enqueue_endpoint():
    runtime = StubRuntime()
    client = _app(runtime).test_client()
    response = client.post(
        "/api/tools/enqueue_crawl",
        json={"url": "https://example.com", "priority": 0.8, "topic": "docs", "reason": "test"},
    )
    assert response.status_code == 200
    assert runtime.enqueued[0]["topic"] == "docs"


def test_fetch_and_reindex():
    runtime = StubRuntime()
    client = _app(runtime).test_client()
    fetch_response = client.post("/api/tools/fetch_page", json={"url": "https://example.com"})
    assert fetch_response.status_code == 200
    reindex_response = client.post("/api/tools/reindex", json={"batch": ["https://example.com"]})
    assert reindex_response.status_code == 200
    assert reindex_response.get_json()["changed"] == 1


def test_status_and_turn():
    runtime = StubRuntime()
    client = _app(runtime).test_client()
    status_resp = client.get("/api/tools/status")
    assert status_resp.status_code == 200
    turn_resp = client.post("/api/tools/agent/turn", json={"query": "test"})
    assert turn_resp.status_code == 200
    assert turn_resp.get_json()["answer"] == "ok"
