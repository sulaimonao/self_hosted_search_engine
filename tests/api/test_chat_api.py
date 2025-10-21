from __future__ import annotations

import json
import logging
from typing import Any
from types import SimpleNamespace

from flask import Flask

from backend.app.api import chat as chat_module
from backend.app.api.chat import bp as chat_bp


class DummyResponse:
    def __init__(
        self,
        lines: list[bytes],
        status_code: int = 200,
        text: str = "",
        json_payload: dict | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self._lines = lines
        self.status_code = status_code
        self.text = text
        self._json = json_payload
        self.headers = headers or {}

    def iter_lines(self):
        yield from self._lines

    def json(self):  # noqa: D401 - mimic requests.Response
        if self._json is None:
            raise ValueError("no json payload provided")
        return self._json

    def close(self):
        return None


def test_schema_parser_allows_user_granted_browser_control():
    payload = {
        "reasoning": "Need live browsing.",
        "answer": "Let me browse for you.",
        "citations": [],
        "autopilot": {
            "mode": "browser",
            "query": "Find latest release notes for Project Atlas",
            "reason": "User granted browser control to help locate the information.",
        },
    }

    serialized = json.dumps(payload)
    parsed = chat_module._coerce_schema(serialized)

    assert parsed["autopilot"] == {
        "mode": "browser",
        "query": "Find latest release notes for Project Atlas",
        "reason": "User granted browser control to help locate the information.",
    }


def test_schema_parser_includes_tool_directives():
    payload = {
        "reasoning": "Tools available.",
        "answer": "Choose an action.",
        "autopilot": {
            "mode": "browser",
            "query": "Open the highlighted article",
            "tools": [
                {
                    "label": "Open in browser",
                    "endpoint": "/api/tools/browser/open",
                    "method": "post",
                    "payload": {"tab_id": "abc123"},
                    "description": "Load the article in the active tab",
                }
            ],
        },
    }

    serialized = json.dumps(payload)
    parsed = chat_module._coerce_schema(serialized)

    assert parsed["autopilot"] == {
        "mode": "browser",
        "query": "Open the highlighted article",
        "reason": None,
        "tools": [
            {
                "label": "Open in browser",
                "endpoint": "/api/tools/browser/open",
                "method": "POST",
                "payload": {"tab_id": "abc123"},
                "description": "Load the article in the active tab",
            }
        ],
    }


def test_chat_logging_records_prompt(caplog, monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(chat_bp)
    app.testing = True

    chat_logger = logging.getLogger("test.chat")
    chat_logger.setLevel(logging.INFO)
    chat_logger.propagate = True
    app.config.update(
        APP_CONFIG=SimpleNamespace(ollama_url="http://ollama"),
        CHAT_LOGGER=chat_logger,
    )

    payload = {
        "model": "llama2",
        "messages": [
            {"role": "user", "content": "Hello world"},
        ],
    }

    streamed_lines = [
        json.dumps({"message": {"content": "Hi"}, "done": False}).encode(),
        json.dumps({"done": True, "total_duration": 1, "load_duration": 1}).encode(),
    ]

    captured = {}

    def fake_post(url, json, stream, timeout):  # noqa: ANN001 - requests compatibility
        captured.update({"url": url, "json": json, "stream": stream, "timeout": timeout})
        return DummyResponse(streamed_lines)

    monkeypatch.setattr(chat_module.requests, "post", fake_post)

    client = app.test_client()
    with caplog.at_level(logging.INFO, logger=chat_logger.name):
        response = client.post("/api/chat", json=payload)
        assert response.status_code == 200
        body = b"".join(response.response)

    assert body
    assert captured["url"] == "http://ollama/api/chat"
    assert captured["json"]["messages"] == payload["messages"]
    assert captured["json"]["model"] == "llama2"

    messages = [record.getMessage() for record in caplog.records if record.name == chat_logger.name]
    assert any("chat request received" in message and "Hello world" in message for message in messages)
    assert any("forwarding chat request to ollama" in message for message in messages)


def test_chat_non_streaming_response(monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(chat_bp)
    app.testing = True

    app.config.update(APP_CONFIG=SimpleNamespace(ollama_url="http://ollama"))

    payload = {
        "model": "llama2",
        "messages": [{"role": "user", "content": "Hi"}],
        "stream": False,
    }

    upstream = {
        "message": {
            "role": "assistant",
            "content": json.dumps({"reasoning": "test", "answer": "Hello there"}),
        }
    }

    captured: dict[str, Any] = {}

    def fake_post(url, json, stream, timeout):  # noqa: ANN001 - requests compatibility
        captured.update({"url": url, "json": json, "stream": stream, "timeout": timeout})
        return DummyResponse([], json_payload=upstream)

    monkeypatch.setattr(chat_module.requests, "post", fake_post)

    client = app.test_client()
    response = client.post("/api/chat", json=payload)
    assert response.status_code == 200
    result = response.get_json()
    assert result["answer"] == "Hello there"
    assert captured["json"]["stream"] is False
    assert captured["stream"] is False
