from __future__ import annotations

import types

import pytest

from backend.app.services import fallbacks


class DummyResponse:
    def __init__(self, url: str, status_code: int, text: str) -> None:
        self.url = url
        self.status_code = status_code
        self.text = text
        self.headers = {}


@pytest.fixture
def stub_requests(monkeypatch):
    calls: dict[str, DummyResponse | None] = {}

    def fake_get(url: str, *_, **__):
        response = calls.get(url)
        if response is None:
            response = DummyResponse(url, 404, "not found")
            calls[url] = response
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(fallbacks.requests, "get", fake_get)
    return calls


def test_smart_fetch_prefers_rss(stub_requests):
    base = "https://example.com"
    feed_url = f"{base}/feed"
    feed_body = """<rss><channel><title>Example</title><item><title>One</title><link>https://example.com/one</link></item></channel></rss>"""
    stub_requests[feed_url] = DummyResponse(feed_url, 200, feed_body)
    result = fallbacks.smart_fetch(base)
    assert result["strategy"] == "rss"
    assert result["items"][0]["url"].endswith("one")


def test_smart_fetch_uses_site_search(stub_requests):
    base = "https://news.test"
    search_url = f"{base}/search?q=hello"
    html = "<html><body><a href=\"/story\">Story</a></body></html>"
    stub_requests[f"{base}/feed"] = DummyResponse(f"{base}/feed", 404, "not found")
    stub_requests[base] = DummyResponse(base, 200, "<html></html>")
    stub_requests[search_url] = DummyResponse(search_url, 200, html)
    result = fallbacks.smart_fetch(base, query="hello")
    assert result["strategy"] == "site_search"
    assert any(item["url"].endswith("/story") for item in result["items"])


def test_smart_fetch_homepage_fallback(stub_requests):
    base = "https://fallback.local"
    homepage = "<html><body><a href=\"https://fallback.local/doc\">Doc</a></body></html>"
    stub_requests[f"{base}/feed"] = DummyResponse(f"{base}/feed", 404, "not found")
    stub_requests[base] = DummyResponse(base, 200, homepage)
    result = fallbacks.smart_fetch(base)
    assert result["strategy"] == "homepage"
    assert result["items"]
