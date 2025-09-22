from __future__ import annotations

import threading
from typing import Any

import pytest

from backend.app.embedding_manager import EmbeddingManager


class DummyResponse:
    def __init__(self, payload: dict[str, Any], *, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.ok = status_code == 200

    def raise_for_status(self) -> None:
        if not self.ok:
            raise RuntimeError("http error")

    def json(self) -> dict[str, Any]:
        return self._payload


def test_list_models_parses_names(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = EmbeddingManager(base_url="http://localhost:11434", embed_model="primary")

    def fake_get(url: str, timeout: float = 0) -> DummyResponse:
        assert url.endswith("/api/tags")
        payload = {
            "models": [
                {"name": "embeddinggemma"},
                {"name": "nomic-embed-text"},
                {"name": ""},
                {"invalid": "entry"},
            ]
        }
        return DummyResponse(payload)

    monkeypatch.setattr("backend.app.embedding_manager.requests.get", fake_get)
    names = manager.list_models()
    assert names == ["embeddinggemma", "nomic-embed-text"]


def test_ensure_transitions_to_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = EmbeddingManager(base_url="http://localhost:11434", embed_model="primary")
    manager.fallbacks = []

    monkeypatch.setattr(manager, "ollama_alive", lambda timeout=1.0: True)
    present_calls = {"count": 0}

    def fake_present(name: str) -> bool:
        present_calls["count"] += 1
        return present_calls["count"] > 1

    def fake_pull(name: str, on_progress=None) -> None:
        if on_progress:
            on_progress(25, "downloading")
            on_progress(80, "verifying")

    monkeypatch.setattr(manager, "model_present", fake_present)
    monkeypatch.setattr(manager, "pull_model", fake_pull)
    monkeypatch.setattr("backend.app.embedding_manager.time.sleep", lambda *_: None)

    status = manager.ensure()
    assert status["state"] == "ready"
    assert status["progress"] == 100
    assert manager.active_model == "primary"


def test_fallback_used_when_primary_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = EmbeddingManager(base_url="http://localhost:11434", embed_model="primary", fallbacks=["fallback"])

    monkeypatch.setattr(manager, "ollama_alive", lambda timeout=1.0: True)

    present_state = {
        "primary": [False, False],
        "fallback": [False, True],
    }

    def fake_present(name: str) -> bool:
        states = present_state.get(name, [True])
        if states:
            value = states.pop(0)
            present_state[name] = states
            return value
        return True

    call_order: list[str] = []

    def fake_pull(name: str, on_progress=None) -> None:
        call_order.append(name)
        if name == "primary":
            raise RuntimeError("download failed")
        if on_progress:
            on_progress(100, "complete")

    monkeypatch.setattr(manager, "model_present", fake_present)
    monkeypatch.setattr(manager, "pull_model", fake_pull)
    monkeypatch.setattr("backend.app.embedding_manager.time.sleep", lambda *_: None)

    status = manager.ensure()
    assert status["state"] == "ready"
    assert status["model"] == "fallback"
    assert call_order == ["primary", "fallback"]


def test_ensure_is_idempotent_during_install(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = EmbeddingManager(base_url="http://localhost:11434", embed_model="primary")
    manager.fallbacks = []

    monkeypatch.setattr(manager, "ollama_alive", lambda timeout=1.0: True)
    monkeypatch.setattr(manager, "model_present", lambda name: False)

    start = threading.Event()
    release = threading.Event()
    pull_calls = {"count": 0}

    def fake_pull(name: str, on_progress=None) -> None:
        pull_calls["count"] += 1
        start.set()
        release.wait(timeout=1)
        raise RuntimeError("pull failed")

    monkeypatch.setattr(manager, "pull_model", fake_pull)
    monkeypatch.setattr("backend.app.embedding_manager.time.sleep", lambda *_: None)

    results: dict[str, dict] = {}

    def installer() -> None:
        results["first"] = manager.ensure()

    thread = threading.Thread(target=installer)
    thread.start()
    assert start.wait(timeout=1)

    interim = manager.ensure()
    assert interim["state"] == "installing"
    assert pull_calls["count"] == 1

    release.set()
    thread.join(timeout=1)
    assert results["first"]["state"] == "error"
    assert pull_calls["count"] == 1

