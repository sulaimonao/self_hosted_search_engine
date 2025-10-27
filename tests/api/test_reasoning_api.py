from __future__ import annotations

from types import SimpleNamespace

import pytest
from flask import Flask

from backend.app.api.reasoning import bp as reasoning_bp


class DummySearchService:
    def run_query(self, query, *, limit, use_llm, model):
        return (
            [
                {
                    "title": "Example",
                    "url": "https://example.com",
                    "summary": f"Snippet for {query}",
                }
            ],
            None,
            {},
        )


def _build_app():
    app = Flask(__name__)
    app.testing = True
    app.register_blueprint(reasoning_bp)
    app.config["SEARCH_SERVICE"] = DummySearchService()
    app.config["RAG_ENGINE_CONFIG"] = SimpleNamespace(
        models=SimpleNamespace(llm_primary="gpt-oss")
    )
    return app


@pytest.fixture(autouse=True)
def _stub_model_resolution(monkeypatch):
    monkeypatch.setattr(
        "backend.app.api.reasoning.ollama_client.resolve_model_name",
        lambda model, **_: model,
    )


def test_reasoning_requires_query():
    app = _build_app()
    client = app.test_client()
    response = client.post("/api/reasoning", json={})
    assert response.status_code == 400


def test_reasoning_returns_autopilot_payload():
    app = _build_app()
    client = app.test_client()
    response = client.post("/api/reasoning", json={"query": "browser test", "use_browser": True})
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["use_browser"] is True
    assert payload["autopilot"]["mode"] == "browser"
    assert payload["browser"]["results"]
