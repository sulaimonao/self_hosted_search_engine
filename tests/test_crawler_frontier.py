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
