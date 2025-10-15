"""Unit tests for the observability helpers."""

from __future__ import annotations

import sys
import types

import observability


def test_start_span_emits_start_and_end_events(monkeypatch):
    events: list[tuple[str, str, dict[str, object]]] = []

    def fake_log_event(level: str, event: str, **kwargs: object) -> None:
        events.append((level, event, kwargs))

    monkeypatch.setattr(observability, "log_event", fake_log_event)
    monkeypatch.setattr(observability, "current_run_log", lambda create=False: None)

    with observability.start_span(
        "unit.test",
        attributes={"foo": "bar"},
        inputs={"payload": 1},
    ) as span:
        span.set_attribute("extra", "value")

    assert [event for _, event, _ in events] == ["unit.test.start", "unit.test.end"]
    assert events[0][0] == "DEBUG"
    assert events[1][0] == "INFO"

    end_event_meta = events[1][2].get("meta")
    assert isinstance(end_event_meta, dict)
    attributes = (
        end_event_meta.get("attributes") if isinstance(end_event_meta, dict) else None
    )
    assert isinstance(attributes, dict)
    assert attributes.get("extra") == "value"
    assert attributes.get("foo") == "bar"


def test_configure_tracing_updates_config(monkeypatch):
    class DummyApp:
        def __init__(self) -> None:
            self.config: dict[str, object] = {}

    app = DummyApp()

    fake_langsmith = types.ModuleType("langsmith")

    class FakeClient:
        def __init__(self) -> None:
            self.initialized = True

    fake_langsmith.Client = FakeClient
    monkeypatch.setitem(sys.modules, "langsmith", fake_langsmith)

    # Reset module globals to deterministic defaults for the test.
    monkeypatch.setattr(observability, "_TRACE_ENABLED", False)
    monkeypatch.setattr(observability, "_PROJECT_NAME", "initial-project")
    monkeypatch.setattr(observability, "_SERVICE_NAME", "initial-service")

    observability.configure_tracing(
        app,
        enabled=True,
        project_name="project-one",
        service_name="service-one",
    )

    assert app.config["OBS_TRACE_ENABLED"] is True
    assert app.config["OBS_TRACE_PROJECT"] == "project-one"
    assert app.config["OBS_TRACE_SERVICE"] == "service-one"

    observability.configure_tracing(
        app,
        enabled=False,
        project_name="project-two",
        service_name="service-two",
    )

    assert app.config["OBS_TRACE_ENABLED"] is False
    assert app.config["OBS_TRACE_PROJECT"] == "project-two"
    assert app.config["OBS_TRACE_SERVICE"] == "service-two"
