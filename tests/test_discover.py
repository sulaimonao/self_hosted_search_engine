import json
from typing import Iterable, Mapping

import pytest

import server.discover as discover
from crawler.frontier import Candidate
from seed_loader.sources import SeedSource
from server.discover import DiscoveryEngine, LLMReranker, extract_links, score_candidate


@pytest.fixture(autouse=True)
def stub_frontier_db(monkeypatch):
    class _DummyDB:
        def domain_value_map(self):
            return {}

    monkeypatch.setattr("crawler.frontier.get_db", lambda: _DummyDB())


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


def test_discovery_engine_merges_sources(monkeypatch):
    def fake_registry(_: Iterable[str] | None) -> list[SeedSource]:
        return [
            SeedSource(
                url="https://docs.alpha.dev",
                source="registry:alpha",
                tags={"registry"},
                metadata={"trust": "high"},
            ),
            SeedSource(
                url="https://beta.dev",
                source="registry:beta",
                tags={"registry"},
                metadata={"trust": "medium"},
            ),
        ]

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


def test_registry_trust_and_extras_affect_scores(monkeypatch):
    registry = [
        SeedSource(
            url="https://alpha.dev/docs",
            source="registry:alpha",
            tags={"registry"},
            metadata={
                "trust": "high",
                "boost": 1.3,
                "value_prior": 2.5,
                "freshness": 0.9,
                "authority": 0.7,
            },
        ),
        SeedSource(
            url="https://beta.dev/docs",
            source="registry:beta",
            tags={"registry"},
            metadata={"trust": "low"},
        ),
    ]

    def fake_registry(_: Iterable[str] | None) -> list[SeedSource]:
        return registry

    engine = DiscoveryEngine(
        registry_loader=fake_registry,
        learned_loader=lambda: [],
        authority_factory=lambda: StubAuthority({"alpha.dev": 0.4, "beta.dev": 0.1}),
        per_host_cap=4,
        politeness_delay=0.0,
    )

    captured: dict[str, list] = {}

    def fake_frontier(query, *, discovery_hints, **kwargs):  # type: ignore[override]
        captured["hints"] = list(discovery_hints)
        return [
            Candidate(url=hit.url, source=hit.source, weight=hit.score or 0.0, score=hit.score)
            for hit in discovery_hints
        ]

    monkeypatch.setattr("crawler.frontier.build_frontier", fake_frontier)

    engine.discover("alpha beta", limit=6, use_llm=False)

    hints = {hit.url: hit for hit in captured["hints"]}
    assert hints["https://alpha.dev/docs"].boost > hints["https://beta.dev/docs"].boost
    assert hints["https://alpha.dev/docs"].value_prior == pytest.approx(2.5)
    assert hints["https://alpha.dev/docs"].freshness == pytest.approx(0.9)
    assert hints["https://alpha.dev/docs"].authority == pytest.approx(0.7)
    assert (hints["https://alpha.dev/docs"].score or 0.0) > (hints["https://beta.dev/docs"].score or 0.0)


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


def test_get_seed_candidates_uses_registry(monkeypatch, tmp_path):
    from backend.app.config import AppConfig
    from backend.app.jobs import focused_crawl

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr(discover, "CURATED_VALUES_PATH", tmp_path / "seeds" / "curated_seeds.jsonl", raising=False)
    monkeypatch.setattr("rank.authority.DEFAULT_AUTHORITY_PATH", tmp_path / "authority.json", raising=False)

    config = AppConfig.from_env()

    captured: dict[str, list] = {}

    def fake_frontier(query, *, discovery_hints, **kwargs):  # type: ignore[override]
        captured["hints"] = list(discovery_hints)
        return [
            Candidate(url=hit.url, source=hit.source, weight=hit.score or 0.0, score=hit.score)
            for hit in discovery_hints
        ]

    monkeypatch.setattr("crawler.frontier.build_frontier", fake_frontier)

    seeds = focused_crawl._get_seed_candidates(
        "python",
        budget=5,
        use_llm=False,
        model=None,
        config=config,
    )

    assert seeds
    assert all(candidate.source != "fallback" for candidate in seeds)
    assert any("docs.python.org" in candidate.url for candidate in seeds)
    assert any(hit.source.startswith("registry:") for hit in captured.get("hints", []))
