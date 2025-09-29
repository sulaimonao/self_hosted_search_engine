from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

from backend.app import create_app


class _FakeResponse:
    def __init__(
        self,
        *,
        status_code: int,
        lines: List[Dict[str, Any]] | None = None,
        text: str = "",
    ) -> None:
        self.status_code = status_code
        self._lines = lines or []
        self._text = text
        self.headers: Dict[str, str] = {}

    def iter_lines(self):  # pragma: no cover - behaviour exercised in tests
        for line in self._lines:
            yield json.dumps(line).encode("utf-8")

    def close(self) -> None:  # pragma: no cover - simple stub
        return None

    @property
    def text(self) -> str:
        return self._text


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    application = create_app()
    return application


def test_chat_retries_with_fallback(monkeypatch: pytest.MonkeyPatch, app) -> None:
    attempts: List[Dict[str, Any]] = []

    responses = [
        _FakeResponse(status_code=404, text='{"error":"model not found"}'),
        _FakeResponse(
            status_code=200,
            lines=[
                {"message": {"content": "Hello"}},
                {"done": True, "total_duration": 123, "load_duration": 45},
            ],
        ),
    ]

    def _fake_post(url: str, json: Dict[str, Any], stream: bool, timeout: int = 0):
        attempts.append(json)
        return responses[len(attempts) - 1]

    monkeypatch.setattr("backend.app.api.chat.requests.post", _fake_post)

    client = app.test_client()
    response = client.post(
        "/api/chat",
        json={"messages": [{"role": "user", "content": "hi"}]},
    )

    body = response.data.decode("utf-8")
    assert response.status_code == 200
    assert "Hello" in body
    assert attempts[0]["model"] == "gpt-oss"
    assert attempts[1]["model"] == "gemma3"
    assert response.headers["X-LLM-Model"] == "gemma3"


def test_chat_returns_model_not_found(monkeypatch: pytest.MonkeyPatch, app) -> None:
    attempts: List[Dict[str, Any]] = []

    def _fake_post(url: str, json: Dict[str, Any], stream: bool, timeout: int = 0):
        attempts.append(json)
        return _FakeResponse(status_code=404, text='{"error":"model not found"}')

    monkeypatch.setattr("backend.app.api.chat.requests.post", _fake_post)

    client = app.test_client()
    response = client.post(
        "/api/chat",
        json={"messages": [{"role": "user", "content": "hi"}]},
    )

    payload = response.get_json()
    assert response.status_code == 503
    assert payload["error"] == "model_not_found"
    assert payload["tried"] == ["gpt-oss", "gemma3"]
    assert "ollama pull" in payload["hint"]
