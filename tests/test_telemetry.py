from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.app import telemetry


LOG_PATH = Path("/tmp/telemetry.log")


def _reset_log() -> None:
    if LOG_PATH.exists():
        LOG_PATH.unlink()


@pytest.mark.usefixtures("monkeypatch")
def test_capture_dev_mode_is_silent(monkeypatch):
    _reset_log()
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("TELEMETRY_ENABLED", raising=False)
    monkeypatch.delenv("TELEMETRY_LOG_LOCAL", raising=False)

    def _should_not_run(event: str, props):  # pragma: no cover - guard
        raise AssertionError("_emit_event should not be called in dev mode")

    monkeypatch.setattr(telemetry, "_emit_event", _should_not_run)
    assert telemetry.capture("dev-test", {"foo": "bar"}) is False
    assert not LOG_PATH.exists()


@pytest.mark.usefixtures("monkeypatch")
def test_capture_dev_mode_logs_locally(monkeypatch):
    _reset_log()
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("TELEMETRY_LOG_LOCAL", "1")
    monkeypatch.delenv("TELEMETRY_ENABLED", raising=False)

    assert telemetry.capture("dev-local", {"key": "value"}, extra=123) is True
    assert LOG_PATH.exists()

    last_line = LOG_PATH.read_text("utf-8").strip().splitlines()[-1]
    payload = json.loads(last_line)
    assert payload["event"] == "dev-local"
    assert payload["properties"] == {"key": "value", "extra": 123}

    _reset_log()


@pytest.mark.usefixtures("monkeypatch")
def test_capture_production_invokes_emitter(monkeypatch):
    _reset_log()
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("TELEMETRY_ENABLED", raising=False)
    monkeypatch.delenv("TELEMETRY_LOG_LOCAL", raising=False)

    recorded: list[tuple[str, dict]] = []

    def _capture(event: str, props):
        recorded.append((event, dict(props)))

    monkeypatch.setattr(telemetry, "_emit_event", _capture)

    assert telemetry.capture("prod-event", foo="bar") is True
    assert recorded == [("prod-event", {"foo": "bar"})]
    assert not LOG_PATH.exists()


@pytest.mark.usefixtures("monkeypatch")
def test_capture_production_swallows_errors(monkeypatch, caplog):
    _reset_log()
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("TELEMETRY_ENABLED", raising=False)
    monkeypatch.delenv("TELEMETRY_LOG_LOCAL", raising=False)

    def _boom(event: str, props):
        raise RuntimeError("boom")

    monkeypatch.setattr(telemetry, "_emit_event", _boom)

    with caplog.at_level("WARNING"):
        assert telemetry.capture("prod-error") is False

    assert "Failed to capture telemetry event" in caplog.text
    assert not LOG_PATH.exists()
