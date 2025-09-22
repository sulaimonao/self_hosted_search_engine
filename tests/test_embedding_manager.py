from __future__ import annotations

import subprocess
import threading
from types import SimpleNamespace

import pytest

from backend.app.embedding_manager import EmbeddingManager


def test_ollama_alive_success(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = EmbeddingManager(base_url="http://localhost:11434", embed_model="primary")

    sample_output = "NAME       STATUS\nembedding  Running\n"

    def fake_run(cmd, **kwargs):
        assert cmd == ["ollama", "ps"]
        assert kwargs.get("capture_output")
        assert kwargs.get("text")
        return SimpleNamespace(stdout=sample_output, returncode=0)

    monkeypatch.setattr("backend.app.embedding_manager.subprocess.run", fake_run)
    assert manager.ollama_alive(timeout=0.5) is True


def test_ollama_alive_handles_cli_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = EmbeddingManager(base_url="http://localhost:11434", embed_model="primary")

    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout", 0))

    monkeypatch.setattr("backend.app.embedding_manager.subprocess.run", fake_run)
    assert manager.ollama_alive(timeout=0.2) is False


def test_list_models_parses_names(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = EmbeddingManager(base_url="http://localhost:11434", embed_model="primary")

    sample_output = "NAME       ID      SIZE\nembeddinggemma  123  1GB\nnomic-embed-text* 456  2GB\n"

    def fake_run(cmd, **kwargs):
        assert cmd == ["ollama", "list"]
        assert kwargs.get("capture_output")
        assert kwargs.get("text")
        return SimpleNamespace(stdout=sample_output, returncode=0)

    monkeypatch.setattr("backend.app.embedding_manager.subprocess.run", fake_run)
    names = manager.list_models()
    assert names == ["embeddinggemma", "nomic-embed-text"]


def test_list_models_handles_cli_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = EmbeddingManager(base_url="http://localhost:11434", embed_model="primary")

    def fake_run(cmd, **kwargs):
        return SimpleNamespace(stdout="", returncode=1)

    monkeypatch.setattr("backend.app.embedding_manager.subprocess.run", fake_run)
    assert manager.list_models() == []


def test_resolve_model_tag_prefers_colon_suffix(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = EmbeddingManager(base_url="http://localhost:11434", embed_model="primary")

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {
                "models": [
                    {"model": "primary:latest"},
                    {"model": "primary:Q4"},
                    {"model": "secondary"},
                ]
            }

    monkeypatch.setattr("backend.app.embedding_manager.requests.get", lambda url, timeout=3: FakeResponse())
    monkeypatch.setattr(manager, "list_models", lambda: [])

    resolved, present = manager.resolve_model_tag("primary")
    assert present is True
    assert resolved == "primary:latest"


def test_refresh_marks_ready_with_resolved_tag(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = EmbeddingManager(base_url="http://localhost:11434", embed_model="primary")

    monkeypatch.setattr(manager, "ollama_alive", lambda timeout=1.0: True)
    monkeypatch.setattr(manager, "resolve_model_tag", lambda name: ("primary:latest", True))

    status = manager.refresh()
    assert status["state"] == "ready"
    assert status["model"] == "primary:latest"
    assert manager.active_model == "primary:latest"


def test_ensure_transitions_to_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = EmbeddingManager(base_url="http://localhost:11434", embed_model="primary")
    manager.fallbacks = []

    monkeypatch.setattr(manager, "ollama_alive", lambda timeout=1.0: True)
    state = {"installed": False}

    def fake_resolve(name: str):
        assert name == "primary"
        if state["installed"]:
            return "primary:latest", True
        return None, False

    def fake_pull(name: str, on_progress=None) -> None:
        if on_progress:
            on_progress(25, "downloading")
            on_progress(80, "verifying")
        state["installed"] = True

    monkeypatch.setattr(manager, "resolve_model_tag", fake_resolve)
    monkeypatch.setattr(manager, "pull_model", fake_pull)
    monkeypatch.setattr("backend.app.embedding_manager.time.sleep", lambda *_: None)

    status = manager.ensure()
    assert status["state"] == "ready"
    assert status["progress"] == 100
    assert status["model"] == "primary:latest"
    assert manager.active_model == "primary:latest"


def test_fallback_used_when_primary_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = EmbeddingManager(base_url="http://localhost:11434", embed_model="primary", fallbacks=["fallback"])

    monkeypatch.setattr(manager, "ollama_alive", lambda timeout=1.0: True)
    state = {"fallback_installed": False}

    def fake_resolve(name: str):
        if name == "primary":
            return None, False
        if name == "fallback":
            if state["fallback_installed"]:
                return "fallback:latest", True
            return None, False
        raise AssertionError(f"unexpected model lookup: {name}")

    call_order: list[str] = []

    def fake_pull(name: str, on_progress=None) -> None:
        call_order.append(name)
        if name == "primary":
            raise RuntimeError("download failed")
        if on_progress:
            on_progress(100, "complete")
        state["fallback_installed"] = True

    monkeypatch.setattr(manager, "resolve_model_tag", fake_resolve)
    monkeypatch.setattr(manager, "pull_model", fake_pull)
    monkeypatch.setattr("backend.app.embedding_manager.time.sleep", lambda *_: None)

    status = manager.ensure()
    assert status["state"] == "ready"
    assert status["model"] == "fallback:latest"
    assert call_order == ["primary", "fallback"]


def test_ensure_is_idempotent_during_install(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = EmbeddingManager(base_url="http://localhost:11434", embed_model="primary")
    manager.fallbacks = []

    monkeypatch.setattr(manager, "ollama_alive", lambda timeout=1.0: True)
    monkeypatch.setattr(manager, "resolve_model_tag", lambda name: (None, False))

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


def test_try_start_attempts_ollama_serve(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = EmbeddingManager(base_url="http://localhost:11434", embed_model="primary")

    popen_calls: list[list[str]] = []

    def fake_popen(cmd, **kwargs):
        popen_calls.append(cmd)
        raise FileNotFoundError("ollama not installed")

    def fake_run(cmd, **kwargs):
        raise FileNotFoundError("service manager unavailable")

    monkeypatch.setattr("backend.app.embedding_manager.subprocess.Popen", fake_popen)
    monkeypatch.setattr("backend.app.embedding_manager.subprocess.run", fake_run)
    monkeypatch.setattr("backend.app.embedding_manager.time.sleep", lambda *_: None)
    monkeypatch.setattr("backend.app.embedding_manager.platform.system", lambda: "Linux")
    monkeypatch.setattr(manager, "resolve_model_tag", lambda name: (None, False))
    monkeypatch.setattr(manager, "ollama_alive", lambda timeout=1.0: False)

    status = manager.ensure()

    assert popen_calls and popen_calls[0] == ["ollama", "serve"]
    assert status["detail"] and "ollama serve spawn failed" in status["detail"]

