from __future__ import annotations

import uuid

import pytest

from backend.app import create_app


@pytest.fixture()
def test_app(monkeypatch: pytest.MonkeyPatch, tmp_path):
    db_path = tmp_path / f"state-{uuid.uuid4().hex}.sqlite3"
    monkeypatch.setenv("APP_STATE_DB_PATH", str(db_path))
    app = create_app()
    app.config.update(TESTING=True)
    return app


def test_progress_stream_route_registered(test_app):
    app = test_app
    routes = {rule.rule for rule in app.url_map.iter_rules()}
    assert "/api/progress/<job_id>/stream" in routes


def test_progress_bus_publish_and_subscribe(test_app):
    app = test_app
    bus = app.config["PROGRESS_BUS"]
    q = bus.subscribe("demo")
    bus.publish("demo", {"stage": "done"})
    event = q.get(timeout=1)
    assert event["stage"] == "done"
