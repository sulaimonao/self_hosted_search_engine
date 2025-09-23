"""Unit tests for registry discovery helpers."""

from __future__ import annotations

import requests

from engine.discovery.gather import RegistryCandidate, gather_from_registry
from server.seeds_loader import SeedRegistryEntry


class FakeResponse:
    def __init__(self, text: str, status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")


def test_gather_from_registry_uses_rss_strategy(monkeypatch):
    entry = SeedRegistryEntry(
        id="rss-test",
        kind="feed",
        strategy="rss_hub",
        entrypoints=(
            "https://example.com/feed.xml",
            "https://fallback.example.net/rss",
        ),
        trust="high",
        extras={"boost": 1.5},
    )

    feed_payload = """
    <rss version="2.0">
      <channel>
        <title>Example Feed</title>
        <item>
          <title>Python Web Scraping Tips</title>
          <link>https://example.com/python-scraping</link>
          <description>Hands-on guide for web scraping.</description>
        </item>
        <item>
          <title>Community Update</title>
          <link>/community</link>
          <description>News unrelated to scraping.</description>
        </item>
      </channel>
    </rss>
    """.strip()

    def fake_get(url, headers, timeout):
        if "example.com" in url:
            return FakeResponse(feed_payload)
        raise requests.RequestException("boom")

    monkeypatch.setattr(
        "engine.discovery.gather.load_seed_registry", lambda: [entry]
    )
    monkeypatch.setattr("engine.discovery.strategies.requests.get", fake_get)

    results = gather_from_registry("Python web scraping", max_candidates=5)
    assert results, "expected registry candidates"
    assert all(isinstance(item, RegistryCandidate) for item in results)

    urls = [item.url for item in results]
    assert "https://example.com/python-scraping" in urls
    assert "https://example.com/community" in urls
    assert "https://fallback.example.net" in urls
    assert len(urls) == len(set(urls)), "candidates should be deduplicated"

    top = results[0]
    assert top.metadata["trust"] == "high"
    assert top.metadata["feed"] == "https://example.com/feed.xml"
    assert top.score > 0
