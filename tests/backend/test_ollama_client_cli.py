"""Unit tests for backend.app.services.ollama_client helpers."""

from __future__ import annotations

import os
from unittest import mock

import pytest

from backend.app.services import ollama_client


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure environment variables from other tests do not leak in."""

    monkeypatch.delenv("OLLAMA_URL", raising=False)


def test_resolve_base_url_prefers_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Explicit base URLs should be returned normalized and override environment."""

    monkeypatch.setenv("OLLAMA_URL", "http://env-host:1234/base/")
    assert (
        ollama_client._resolve_base_url("http://custom-host:9999//")
        == "http://custom-host:9999"
    )


def test_resolve_base_url_falls_back_to_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """When no explicit value is provided, ``OLLAMA_URL`` should be used."""

    monkeypatch.setenv("OLLAMA_URL", "http://env-host:2345")
    assert ollama_client._resolve_base_url() == "http://env-host:2345"


def test_pull_model_injects_ollama_host(monkeypatch: pytest.MonkeyPatch) -> None:
    """``pull_model`` must inject ``OLLAMA_HOST`` so the CLI targets the same base."""

    fake_env = {"SOME_FLAG": "1"}
    popen_mock = mock.Mock()
    monkeypatch.setenv("OLLAMA_URL", "http://cli-host:8080")
    monkeypatch.setattr(
        ollama_client.subprocess, "Popen", popen_mock, raising=True
    )

    ollama_client.pull_model("test-model", env=fake_env)

    assert popen_mock.call_count == 1
    args, kwargs = popen_mock.call_args
    assert list(args[0]) == ["ollama", "pull", "test-model"]
    passed_env = kwargs.get("env") or os.environ
    assert passed_env["OLLAMA_HOST"] == "http://cli-host:8080"
    assert passed_env["SOME_FLAG"] == "1"
    assert fake_env == {"SOME_FLAG": "1"}
