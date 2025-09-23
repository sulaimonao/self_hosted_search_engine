from __future__ import annotations

import json
import logging
from types import SimpleNamespace

from flask import Flask

from backend.app.api import chat as chat_module
from backend.app.api.chat import bp as chat_bp


class DummyResponse:
    def __init__(self, lines: list[bytes], status_code: int = 200, text: str = "") -> None:
        self._lines = lines
        self.status_code = status_code
        self.text = text

    def iter_lines(self):
        yield from self._lines


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
