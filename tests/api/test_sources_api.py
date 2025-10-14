from __future__ import annotations

import uuid

import pytest
from flask import Flask

from backend.app.api.sources import bp as sources_bp
from backend.app.db import AppStateDB


def _setup_app(monkeypatch: pytest.MonkeyPatch, tmp_path):
    db_path = tmp_path / f"state-{uuid.uuid4().hex}.sqlite3"
    state_db = AppStateDB(db_path)
    app = Flask(__name__)
    app.config["APP_STATE_DB"] = state_db
    app.register_blueprint(sources_bp)
    return app, app.test_client(), state_db


def test_sources_config_get_and_post(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    app, client, state_db = _setup_app(monkeypatch, tmp_path)

    response = client.get("/api/sources/config")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["config"]["enabled"] is False

    update = {
        "enabled": True,
        "max_depth": 2,
        "max_sources_per_page": 4,
        "max_total_sources": 10,
        "allowed_domains": ["example.com"],
        "file_types": ["pdf", "html"],
    }
    post_response = client.post("/api/sources/config", json=update)
    assert post_response.status_code == 200
    body = post_response.get_json()
    assert body["ok"] is True
    assert body["config"]["enabled"] is True

    persisted = state_db.get_sources_config()
    assert persisted.enabled is True
    assert persisted.allowed_domains == ["example.com"]


def test_sources_config_rejects_invalid_payload(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    app, client, _ = _setup_app(monkeypatch, tmp_path)
    resp = client.post("/api/sources/config", json=["invalid"])
    assert resp.status_code == 400
