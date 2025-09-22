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
    monkeypatch.setattr(manager, "ollama_alive", lambda timeout=1.0: False)

    status = manager.ensure()

    assert popen_calls and popen_calls[0] == ["ollama", "serve"]
    assert status["detail"] and "ollama serve spawn failed" in status["detail"]

