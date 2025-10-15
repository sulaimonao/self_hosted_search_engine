"""Tests for the Ollama JSON client concurrency guarantees."""

from __future__ import annotations

import json as jsonlib
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Iterable

import pytest

from server.llm import OllamaJSONClient


class _SerialSession:
    """Session stub that fails when used concurrently."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.get_calls = 0
        self.post_calls = 0

    def _acquire(self) -> None:
        if not self._lock.acquire(blocking=False):  # pragma: no cover - defensive
            raise AssertionError("session accessed concurrently")

    def _release(self) -> None:
        self._lock.release()

    def get(self, url: str, timeout: float) -> "_FakeResponse":
        self._acquire()
        try:
            self.get_calls += 1
            time.sleep(0.01)
            return _FakeResponse({"models": [{"name": "llama3"}]})
        finally:
            self._release()

    def post(
        self,
        url: str,
        json: dict[str, Any] | None = None,
        timeout: float = 0.0,
    ) -> "_FakeResponse":
        self._acquire()
        try:
            self.post_calls += 1
            time.sleep(0.01)
            if url.endswith("/api/chat"):
                response_payload = {
                    "message": {
                        "content": jsonlib.dumps(
                            {
                                "type": "final",
                                "answer": "ok",
                                "sources": [],
                            }
                        )
                    }
                }
            else:  # pragma: no cover - unexpected endpoint
                response_payload = {}
            return _FakeResponse(response_payload)
        finally:
            self._release()


class _FakeResponse:
    def __init__(self, payload: dict[str, Any], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = jsonlib.dumps(payload)

    def raise_for_status(self) -> None:
        if not (200 <= self.status_code < 300):  # pragma: no cover - defensive
            raise AssertionError("unexpected status")

    def json(self) -> dict[str, Any]:
        return self._payload


@pytest.mark.parametrize("refresh", [True, False])
def test_list_models_serializes_session_access(refresh: bool) -> None:
    session = _SerialSession()
    client = OllamaJSONClient(base_url="http://localhost", session=session)

    def _call() -> list[str]:
        return client.list_models(refresh=refresh)

    with ThreadPoolExecutor(max_workers=4) as pool:
        results: list[list[str]] = list(pool.map(lambda _: _call(), range(6)))

    assert all(result == ["llama3"] for result in results)
    # ``refresh=False`` should rely on caching after the first request.
    if refresh:
        assert session.get_calls == len(results)
    else:
        assert session.get_calls == 1


def test_chat_json_serializes_session_access() -> None:
    session = _SerialSession()
    client = OllamaJSONClient(base_url="http://localhost", session=session)
    messages: Iterable[dict[str, str]] = [{"role": "user", "content": "hi"}]

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: client.chat_json(messages), range(6)))

    assert all(result["answer"] == "ok" for result in results)
    assert session.post_calls == len(results)
