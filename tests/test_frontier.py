import types

import pytest

from urllib.parse import urlparse

from rank.authority import AuthorityIndex
from search.frontier import build_frontier


class DummyAuthority:
    def __init__(self, scores):
        self.scores = scores

    def score_for(self, url_or_host: str) -> float:
        parsed = urlparse(url_or_host)
        host = parsed.netloc or url_or_host
        return self.scores.get(host, 0.0)


@pytest.fixture(autouse=True)
def patch_authority(monkeypatch):
    dummy = DummyAuthority({"high.com": 5.0, "low.com": 0.1})
    monkeypatch.setattr(AuthorityIndex, "load_default", classmethod(lambda cls: dummy))
    return dummy


def test_frontier_prioritises_high_value(monkeypatch):
    value_overrides = {"high.com": 2.0, "low.com": 0.1}
    candidates = build_frontier(
        "docs",
        seed_domains=["high.com", "low.com"],
        extra_urls=["https://misc.dev/docs"],
        budget=5,
        value_overrides=value_overrides,
    )
    assert candidates, "expected candidate URLs"
    scores = [candidate.priority for candidate in candidates]
    assert scores == sorted(scores, reverse=True)
    top = candidates[0]
    assert "high.com" in top.url
