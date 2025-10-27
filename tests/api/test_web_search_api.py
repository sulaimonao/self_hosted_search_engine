from __future__ import annotations

from flask import Flask

from backend.app.api.web_search import bp as web_search_bp, web_search


class DummySearchService:
    def run_query(self, query, *, limit, use_llm, model):  # noqa: D401 - test stub
        return (
            [
                {
                    "title": f"Result for {query}",
                    "url": "https://example.com",
                    "summary": "Example snippet",
                }
            ],
            None,
            {},
        )


def _build_app(service) -> Flask:
    app = Flask(__name__)
    app.testing = True
    app.register_blueprint(web_search_bp)
    app.config["SEARCH_SERVICE"] = service
    return app


def test_web_search_returns_results():
    app = _build_app(DummySearchService())
    with app.app_context():
        results = web_search("alpha")
    assert results and results[0]["url"] == "https://example.com"


def test_web_search_returns_fallback_when_empty():
    class EmptySearch:
        def run_query(self, *args, **kwargs):
            return ([], None, {})

    app = _build_app(EmptySearch())
    with app.app_context():
        results = web_search("alpha")
    assert results and results[0]["title"] == "No live data retrieved"


def test_web_search_endpoint():
    app = _build_app(DummySearchService())
    client = app.test_client()
    response = client.get("/api/web-search?q=browser")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["results"]
