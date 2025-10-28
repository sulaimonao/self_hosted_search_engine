"""Unit tests covering the LLM models API."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path
from typing import Any

import pytest

from engine.config import EngineConfig

app_module = import_module("backend.app.__init__")


class _FakeResponse:
    def __init__(self, *, payload: dict[str, Any] | None = None, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:  # pragma: no cover - trivial
        return None

    def json(self) -> dict[str, Any]:
        if self._payload is None:
            raise ValueError("No JSON payload available")
        return self._payload


def _fake_requests_get(url: str, timeout: int) -> _FakeResponse:  # noqa: D401 - simple wrapper
    del timeout
    if url.endswith("/api/tags"):
        return _FakeResponse(
            payload={
                "models": [
                    {"name": "llama3.1:8b"},
                    {"name": "text-embedding-3-large"},
                    {"name": "nomic-embed-text"},
                    {"name": "gte-small"},
                    {"name": "bge-base"},
                    {"name": "mxbai-embed-large"},
                    "phi4",
                ]
            }
        )
    return _FakeResponse(status_code=200)


def test_llm_models_returns_configured_primary_and_embed(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Ensure configured models lead the response and extras are appended."""

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr(app_module.requests, "get", _fake_requests_get)

    app = app_module.create_app()
    app.config["RAG_ENGINE_CONFIG"] = EngineConfig.from_yaml(Path("config.yaml"))
    client = app.test_client()

    response = client.get("/api/llm/models")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ollama_host"].startswith("http://127.0.0.1")

    chat_models = payload["chat_models"]
    assert "llama3.1:8b" in chat_models
    assert "phi4" in chat_models
    assert all("embed" not in name for name in chat_models)

    configured = payload["configured"]
    assert configured["primary"] == "gpt-oss"
    assert configured["fallback"] == "gemma3"
    assert payload["embedder"] == "embeddinggemma"


def test_llm_health_reports_reachability(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr(app_module.requests, "get", _fake_requests_get)

    app = app_module.create_app()
    client = app.test_client()

    response = client.get("/api/llm/health")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["reachable"] is True
    assert payload["model_count"] == 7


def test_autopull_disabled_without_flag(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("DEV_ALLOW_AUTOPULL", raising=False)
    app = app_module.create_app()
    client = app.test_client()

    response = client.post("/api/llm/autopull", json={"candidates": ["gemma3"]})
    assert response.status_code == 403
    payload = response.get_json()
    assert payload["error"] == "autopull_disabled"
