from __future__ import annotations

from types import SimpleNamespace

from flask import Flask

from backend.app.api import search as search_module

from backend.app.api.search import bp as search_bp
from engine.agents.rag import RagResult
from engine.data.store import RetrievedChunk


class StubEmbedder:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.model = "test-embed"
        self.model_updates: list[str] = []

    def set_model(self, model: str) -> None:
        self.model = model
        self.model_updates.append(model)

    def embed_query(self, text: str):
        self.calls.append(text)
        return [0.1, 0.2]


class StubEmbeddingManager:
    def __init__(self, status: dict | None = None) -> None:
        self.status = status or {"state": "ready", "model": "test-embed", "progress": 100}
        self.wait_calls = 0
        self.ensure_calls = 0
        self.status_calls = 0

    def wait_until_ready(self):
        self.wait_calls += 1
        return self.status

    def ensure(self, model: str | None = None):
        self.ensure_calls += 1
        return self.status

    def get_status(self, refresh: bool = False):
        self.status_calls += 1
        return self.status


class StubStore:
    def __init__(self, results: list[RetrievedChunk]):
        self._results = results
        self.queries: int = 0

    def query(self, **kwargs):
        self.queries += 1
        return list(self._results)


class ColdStartSpy:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def build_index(self, query: str, *, use_llm: bool = False, llm_model: str | None = None):
        self.calls.append({"query": query, "use_llm": use_llm, "llm_model": llm_model})
        return 0


class StubRagAgent:
    def run(self, question: str, documents):
        return RagResult(
            answer="Summary answer",
            sources=[{"id": 1, "url": "https://example.com", "title": "Example", "similarity": 0.91}],
            used=len(documents),
        )


def _base_config():
    return SimpleNamespace(
        models=SimpleNamespace(embed="test-embed"),
        retrieval=SimpleNamespace(k=3, min_hits=0, similarity_threshold=0.1),
        ollama=SimpleNamespace(base_url="http://localhost:11434"),
    )


def _build_app(store, coldstart, rag_agent, *, embed_manager=None, engine_config=None):
    app = Flask(__name__)
    app.register_blueprint(search_bp)
    config = engine_config or _base_config()
    manager = embed_manager or StubEmbeddingManager()
    embedder = StubEmbedder()
    app.config.update(
        RAG_ENGINE_CONFIG=config,
        RAG_VECTOR_STORE=store,
        RAG_EMBEDDER=embedder,
        RAG_COLDSTART=coldstart,
        RAG_AGENT=rag_agent,
        RAG_EMBED_MODEL_NAME=config.models.embed,
        RAG_OLLAMA_HOST=config.ollama.base_url,
        RAG_EMBED_MANAGER=manager,
    )
    app.testing = True
    return app


def test_search_service_endpoint_returns_job_id_with_results():
    class StubSearchService:
        def __init__(self) -> None:
            self.calls: list[tuple[str, int, bool, str | None]] = []

        def run_query(self, query: str, *, limit: int, use_llm: bool, model: str | None):
            self.calls.append((query, limit, use_llm, model))
            return (
                [
                    {
                        "url": "https://docs.example.com",
                        "title": "Example Doc",
                        "snippet": "Sample snippet",
                        "score": 1.0,
                        "lang": "en",
                    }
                ],
                "job-123",
                {"confidence": 0.1, "triggered": True, "trigger_reason": "no_results", "seed_count": 0},
            )

        def last_index_time(self) -> int:
            return 1700000000

    search_service = StubSearchService()
    app = Flask(__name__)
    app.register_blueprint(search_bp)
    app.config.update(
        SEARCH_SERVICE=search_service,
        APP_CONFIG=SimpleNamespace(search_default_limit=5, smart_min_results=1),
    )
    app.testing = True

    client = app.test_client()
    response = client.get("/api/search", query_string={"q": "docs"})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ok"
    assert payload["job_id"] == "job-123"
    assert payload["results"][0]["url"] == "https://docs.example.com"
    assert payload["last_index_time"] == search_service.last_index_time()
    assert search_service.calls == [("docs", 5, False, None)]
    assert "confidence" in payload


def test_search_returns_answer_and_results():
    chunks = [
        RetrievedChunk(
            text="This is a retrieved chunk of content that answers the query.",
            title="Test Document",
            url="https://docs.example.com",
            similarity=0.87,
        )
    ]
    store = StubStore(chunks)
    coldstart = ColdStartSpy()
    rag_agent = StubRagAgent()
    app = _build_app(store, coldstart, rag_agent)

    client = app.test_client()
    response = client.get("/api/search", query_string={"q": "test"})
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ok"
    assert payload["answer"] == "Summary answer"
    assert payload["k"] == 1
    assert payload["results"]
    first = payload["results"][0]
    assert first["url"] == "https://docs.example.com"
    assert "snippet" in first and first["snippet"].startswith("This is")
    assert coldstart.calls == []


def test_search_triggers_coldstart_when_insufficient_hits():
    store = StubStore([])
    coldstart = ColdStartSpy()

    class RejectingRag:
        def run(self, question, documents):  # pragma: no cover - should not execute
            raise AssertionError("RAG should not run when no documents are returned")

    engine_config = SimpleNamespace(
        models=SimpleNamespace(embed="test-embed"),
        retrieval=SimpleNamespace(k=3, min_hits=2, similarity_threshold=0.1),
        ollama=SimpleNamespace(base_url="http://localhost:11434"),
    )

    app = _build_app(store, coldstart, RejectingRag(), engine_config=engine_config)
    client = app.test_client()

    response = client.get("/api/search", query_string={"q": "need data"})
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "no_results"
    assert payload["llm_used"] is False
    assert coldstart.calls
    call = coldstart.calls[0]
    assert call == {"query": "need data", "use_llm": False, "llm_model": None}


def test_search_returns_planner_payload_when_llm_enabled(monkeypatch):
    store = StubStore([])
    coldstart = ColdStartSpy()
    rag_agent = StubRagAgent()
    app = _build_app(store, coldstart, rag_agent)

    captured: dict[str, tuple[str, str | None]] = {}

    def _fake_run_agent(query: str, *, model: str | None = None, context=None):
        captured["args"] = (query, model)
        return {
            "type": "final",
            "answer": "Planner summary",
            "sources": [],
            "steps": [],
            "llm_used": True,
            "llm_model": model,
        }

    monkeypatch.setattr(search_module, "run_agent", _fake_run_agent)

    client = app.test_client()
    response = client.get(
        "/api/search",
        query_string={"q": "need data", "llm": "on", "model": "llama"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["type"] == "final"
    assert payload["llm_model"] == "llama"
    assert captured["args"] == ("need data", "llama")


def test_search_reports_embedding_unavailable():
    chunks = []
    store = StubStore([])
    coldstart = ColdStartSpy()
    rag_agent = StubRagAgent()
    status = {
        "state": "error",
        "model": "test-embed",
        "error": "ollama_offline",
        "detail": "offline",
        "fallbacks": ["alt-model"],
    }
    manager = StubEmbeddingManager(status)
    app = _build_app(store, coldstart, rag_agent, embed_manager=manager)
    client = app.test_client()

    response = client.get("/api/search", query_string={"q": "test"})
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "warming"
    assert payload["code"] == "embedding_unavailable"
    assert payload["action"] == "ollama pull test-embed"
    assert payload["embedder_status"]["state"] == "error"
    assert payload["fallbacks"] == ["alt-model"]
    assert "detail" in payload
    assert payload["llm_used"] is False


def test_embedder_status_endpoint_returns_manager_state():
    store = StubStore([])
    coldstart = ColdStartSpy()
    rag_agent = StubRagAgent()
    status = {"state": "installing", "progress": 42, "model": "test-embed"}
    manager = StubEmbeddingManager(status)
    app = _build_app(store, coldstart, rag_agent, embed_manager=manager)
    client = app.test_client()

    response = client.get("/api/embedder/status")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["state"] == "installing"
    assert manager.status_calls >= 1


def test_embedder_ensure_endpoint_triggers_manager():
    store = StubStore([])
    coldstart = ColdStartSpy()
    rag_agent = StubRagAgent()
    manager = StubEmbeddingManager({"state": "ready", "model": "fallback"})
    app = _build_app(store, coldstart, rag_agent, embed_manager=manager)
    client = app.test_client()

    response = client.post("/api/embedder/ensure", json={"model": "fallback"})
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["model"] == "fallback"
    assert manager.ensure_calls >= 1
