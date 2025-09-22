from types import SimpleNamespace
from urllib.parse import urlparse

import pytest

from crawler.frontier import build_frontier


def test_crawler_frontier_applies_value_overrides_before_dedupe():
    candidates = build_frontier(
        "docs",
        extra_urls=["https://preferred.com/docs/"],
        seed_domains=["preferred.com"],
        budget=5,
        value_overrides={"preferred.com": 4.0},
    )

    assert candidates, "expected crawler frontier candidates"

    target = next(
        candidate
        for candidate in candidates
        if urlparse(candidate.url).netloc == "preferred.com"
        and candidate.url.startswith("https://preferred.com/docs")
    )

    assert target.weight == pytest.approx(4.0)
    assert target.score == pytest.approx(4.0)


def test_crawler_frontier_legacy_arguments_still_supported():
    candidates = build_frontier(
        "docs",
        extra_urls=["preferred.com"],
        budget=3,
    )

    assert candidates, "expected crawler frontier candidates"

    domain_candidate = next(
        candidate
        for candidate in candidates
        if urlparse(candidate.url).netloc == "preferred.com"
    )

    assert domain_candidate.weight == pytest.approx(1.5)
    assert domain_candidate.score == pytest.approx(domain_candidate.weight)


def test_crawler_frontier_enforces_host_cap():
    hints = [
        SimpleNamespace(url=f"https://preferred.com/docs/{idx}", source="seed", score=2.0, boost=1.0)
        for idx in range(4)
    ]
    hints.extend(
        [SimpleNamespace(url=f"https://alt{idx}.dev/docs", source="seed", score=1.5, boost=1.0) for idx in range(2)]
    )

    candidates = build_frontier(
        "docs",
        discovery_hints=hints,
        budget=5,
        per_host_cap=2,
    )

    preferred = [c for c in candidates if urlparse(c.url).netloc == "preferred.com"]
    assert len(preferred) == 2


def test_crawler_frontier_politeness_delay_sets_available_at():
    hints = [
        SimpleNamespace(url=f"https://timed.dev/docs/{idx}", source="seed", score=3.0 - idx * 0.1, boost=1.0)
        for idx in range(3)
    ]
    candidates = build_frontier(
        "timed",
        discovery_hints=hints,
        budget=3,
        per_host_cap=3,
        politeness_delay=5.0,
        now=0.0,
    )
    times = [c.available_at for c in candidates]
    assert times == [0.0, 5.0, 10.0]


def test_crawler_frontier_reranks_borderline_candidates():
    hints = [
        SimpleNamespace(url=f"https://rr{i}.dev/docs", source="seed", score=1.0 + i * 0.01, boost=1.0)
        for i in range(4)
    ]

    def rerank(query, items):
        assert query == "rr"
        return list(reversed(items))

    candidates = build_frontier(
        "rr",
        discovery_hints=hints,
        budget=4,
        per_host_cap=4,
        rerank_fn=rerank,
        rerank_margin=0.5,
    )

    assert [c.url for c in candidates[:2]] == [
        "https://rr0.dev/docs",
        "https://rr1.dev/docs",
    ]
