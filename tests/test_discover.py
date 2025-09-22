import json
from typing import Iterable, Mapping

import pytest

import server.discover as discover
from crawler.frontier import Candidate
from server.discover import DiscoveryEngine, LLMReranker, extract_links, score_candidate


def test_extract_links_handles_relative_urls():
    html = """
    <html><body>
        <a href="https://example.com/docs/">Docs</a>
        <a href="/guides/intro">Guide</a>
        <a href="javascript:void(0)">Skip</a>
    </body></html>
    """
    links = extract_links(html, base_url="https://example.com")
    assert links == [
        "https://example.com/docs",
        "https://example.com/guides/intro",
    ]


def test_score_candidate_respects_weights():
    value = score_candidate(boost=1.0, value_prior=1.0, freshness=0.5, authority=0.25)
    expected = (
        discover.BASE_WEIGHT * 1.0
        + discover.VALUE_WEIGHT * 1.0
        + discover.FRESH_WEIGHT * 0.5
        + discover.AUTH_WEIGHT * 0.25
    )
    assert value == pytest.approx(expected)


class StubAuthority:
    def __init__(self, scores: Mapping[str, float]) -> None:
        self.scores = scores

    def score_for(self, host: str) -> float:
        return self.scores.get(host, 0.0)


class StubSeed:
    def __init__(self, url: str, source: str = "seed") -> None:
        self.url = url
        self.source = source
        self.tags: set[str] = set()


def test_discovery_engine_merges_sources(monkeypatch):
    def fake_registry(_: Iterable[str] | None) -> list[StubSeed]:
        return [StubSeed("https://docs.alpha.dev"), StubSeed("https://beta.dev")]

    learned = [
        {"domain": "gamma.dev", "score": 1.2, "url": "https://gamma.dev/docs"},
    ]

    engine = DiscoveryEngine(
        registry_loader=fake_registry,
        learned_loader=lambda: learned,
        authority_factory=lambda: StubAuthority({"docs.alpha.dev": 0.5, "gamma.dev": 0.2}),
        per_host_cap=3,
        politeness_delay=0.0,
    )

    frontier = engine.discover(
        "alpha",
        limit=5,
        extra_seeds=["https://handbook.alpha.dev"],
        use_llm=False,
    )

    urls = [candidate.url for candidate in frontier]
    assert any(url.startswith("https://docs.alpha.dev") for url in urls)
    assert any("gamma.dev" in url for url in urls)
    assert all(candidate.score is not None for candidate in frontier)


def test_llm_reranker_orders_candidates(monkeypatch):
    class DummyResponse:
        def __init__(self, order):
            self._order = order

        def raise_for_status(self):
            return None

        def json(self):
            return {"response": json.dumps(self._order)}

    calls = {}

    def fake_transport(url, *, json, timeout):
        calls["url"] = url
        return DummyResponse(["https://b.dev", "https://a.dev"])

    reranker = LLMReranker("http://localhost:11434", model="stub", transport=fake_transport)
    candidates = [
        Candidate(url="https://a.dev", source="seed", weight=1.0, score=1.0),
        Candidate(url="https://b.dev", source="seed", weight=1.0, score=1.0),
    ]

    ranked = reranker("query", candidates)
    assert ranked[0].url == "https://b.dev"
    assert calls["url"].endswith("/api/generate")
