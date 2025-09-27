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


def test_embed_model_normalization(monkeypatch):
    import importlib

    captured_models = []

    def _capture_model(expected_model_env: str) -> None:
        monkeypatch.setenv("EMBED_MODEL", expected_model_env)
        importlib.reload(adapter)

        def _mock_post(url, json, timeout):
            captured_models.append(json["model"])
            return _MockResponse(status_code=200, json=lambda: {"embedding": [0.0]})

        monkeypatch.setattr(adapter.httpx, "post", _mock_post)
        adapter.embed_texts(["hello"])

    _capture_model("embeddinggemma")
    _capture_model("embedding-gemma")

    assert captured_models == ["embeddinggemma", "embeddinggemma"]

    monkeypatch.delenv("EMBED_MODEL", raising=False)
    importlib.reload(adapter)
