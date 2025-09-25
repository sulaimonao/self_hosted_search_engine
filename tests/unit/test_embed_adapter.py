from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.embed import adapter


class _MockResponse(SimpleNamespace):
    def raise_for_status(self) -> None:  # pragma: no cover - no failure path in tests
        if getattr(self, "status_code", 200) >= 400:
            raise RuntimeError("boom")


def test_embed_texts_success(monkeypatch):
    def _mock_post(url, json, timeout):  # noqa: D401 - signature matches httpx.post
        assert json["input"] == ["hello"]
        return _MockResponse(
            status_code=200,
            json=lambda: {"data": [{"embedding": [0.1, 0.2, 0.3]}]},
        )

    monkeypatch.setattr(adapter.httpx, "post", _mock_post)
    vectors = adapter.embed_texts(["hello"])
    assert vectors == [[0.1, 0.2, 0.3]]


def test_embed_texts_failure(monkeypatch):
    def _mock_post(url, json, timeout):  # noqa: D401 - signature matches httpx.post
        raise RuntimeError("network down")

    monkeypatch.setattr(adapter.httpx, "post", _mock_post)
    assert adapter.embed_texts(["hello"]) is None


def test_embed_texts_empty_input(monkeypatch):
    # ensure no HTTP call when input collapses to empty list
    monkeypatch.setattr(adapter.httpx, "post", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("should not call")))
    assert adapter.embed_texts([" "]) == []
