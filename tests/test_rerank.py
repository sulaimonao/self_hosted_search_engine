import requests

from rank.blend import maybe_rerank


def test_rerank_noop_without_llm(monkeypatch):
    def fake_post(*args, **kwargs):
        raise requests.RequestException("offline")

    monkeypatch.setattr("requests.post", fake_post)
    docs = [{"url": "https://example.com", "title": "Example", "snippet": "Text"}]
    reranked = maybe_rerank("query", docs, enabled=True, model="fake", timeout=0.1)
    assert reranked is docs
