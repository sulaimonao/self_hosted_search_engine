from __future__ import annotations

import json

from backend.app import telemetry


def test_capture_writes_events(monkeypatch, tmp_path):
    log_path = tmp_path / "events.ndjson"
    monkeypatch.setenv("TELEMETRY_EVENTS_PATH", str(log_path))
    assert telemetry.capture("unit-test", {"foo": "bar"}) is True
    assert log_path.exists()
    payloads = [json.loads(line) for line in log_path.read_text("utf-8").splitlines()]
    assert payloads[0]["event"] == "unit-test"
    assert payloads[0]["properties"] == {"foo": "bar"}


def test_capture_merges_kwargs(monkeypatch, tmp_path):
    log_path = tmp_path / "events.ndjson"
    monkeypatch.setenv("TELEMETRY_EVENTS_PATH", str(log_path))
    telemetry.capture("merge-test", {"foo": "bar"}, extra=123)
    payload = json.loads(log_path.read_text("utf-8").strip())
    assert payload["properties"] == {"foo": "bar", "extra": 123}


def test_capture_requires_event_name(monkeypatch, tmp_path):
    log_path = tmp_path / "events.ndjson"
    monkeypatch.setenv("TELEMETRY_EVENTS_PATH", str(log_path))
    assert telemetry.capture("", foo="bar") is False
    assert not log_path.exists()
