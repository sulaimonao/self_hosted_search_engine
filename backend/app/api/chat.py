"""LLM chat endpoint streaming responses from Ollama via SSE."""

from __future__ import annotations

import json
from typing import Iterable, Iterator

import requests
from flask import Blueprint, Response, current_app, request, stream_with_context

from ..config import AppConfig

bp = Blueprint("chat_api", __name__, url_prefix="/api")


def _ollama_chat_stream(url: str, payload: dict) -> Iterable[str]:
    try:
        response = requests.post(url, json=payload, stream=True, timeout=120)
    except requests.RequestException as exc:
        message = json.dumps({"type": "error", "content": str(exc)})
        yield f"data: {message}\n\n"
        return

    if response.status_code >= 400:
        content = response.text.strip() or f"HTTP {response.status_code}"
        message = json.dumps({"type": "error", "content": content})
        yield f"data: {message}\n\n"
        return

    for line in response.iter_lines():
        if not line:
            continue
        try:
            chunk = json.loads(line.decode("utf-8"))
        except json.JSONDecodeError:
            continue
        message = chunk.get("message", {})
        content = message.get("content")
        if content:
            yield f"data: {json.dumps({'type': 'token', 'content': content})}\n\n"
        if chunk.get("done"):
            final = {
                "type": "done",
                "total_duration": chunk.get("total_duration"),
                "load_duration": chunk.get("load_duration"),
            }
            yield f"data: {json.dumps(final)}\n\n"
            break


@bp.post("/chat")
def chat_stream() -> Response:
    payload = request.get_json(silent=True) or {}
    messages = payload.get("messages")
    if not isinstance(messages, list):
        return Response(json.dumps({"error": "messages must be a list"}), status=400, mimetype="application/json")
    model = (payload.get("model") or "").strip() or None

    config: AppConfig = current_app.config["APP_CONFIG"]
    url = f"{config.ollama_url}/api/chat"
    body = {"messages": messages, "stream": True}
    if model:
        body["model"] = model

    def generate() -> Iterator[str]:
        yield from _ollama_chat_stream(url, body)

    return Response(stream_with_context(generate()), mimetype="text/event-stream")
