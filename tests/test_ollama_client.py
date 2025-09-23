"""Tests for the Ollama HTTP client helpers."""

from __future__ import annotations

import pytest

from engine.llm.ollama_client import (
    ChatMessage,
    OllamaClient,
    OllamaClientError,
    _message_to_dict,
)


def test_message_to_dict_from_mapping() -> None:
    message = {"role": "user", "content": "hello"}

    assert _message_to_dict(message) == {"role": "user", "content": "hello"}


def test_message_to_dict_from_dataclass() -> None:
    message = ChatMessage(role="assistant", content="Hi there")

    assert _message_to_dict(message) == {"role": "assistant", "content": "Hi there"}


def test_message_to_dict_from_attribute_object() -> None:
    class AttrMessage:
        def __init__(self, role: str, content: str) -> None:
            self.role = role
            self.content = content

    message = AttrMessage(role="system", content="Remember the rules")

    assert _message_to_dict(message) == {
        "role": "system",
        "content": "Remember the rules",
    }


def test_message_to_dict_from_model_dump() -> None:
    class FakePydanticModel:
        def __init__(self, role: str, content: str) -> None:
            self.role = role
            self.content = content

        def model_dump(self) -> dict[str, str]:
            return {"role": self.role, "content": self.content}

    message = FakePydanticModel(role="system", content="Ready")

    assert _message_to_dict(message) == {"role": "system", "content": "Ready"}


def test_chat_raises_for_blank_response_content() -> None:
    client = OllamaClient(base_url="http://ollama.local")

    class StubResponse:
        status_code = 200

        def raise_for_status(self) -> None:  # pragma: no cover - API compatibility
            return None

        @staticmethod
        def json() -> dict[str, dict[str, str]]:
            return {"message": {"content": "   "}}

    class StubSession:
        def post(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            return StubResponse()

    client._session = StubSession()  # type: ignore[assignment]

    with pytest.raises(OllamaClientError):
        client.chat(model="llama3", messages=[ChatMessage(role="user", content="Hi")])
