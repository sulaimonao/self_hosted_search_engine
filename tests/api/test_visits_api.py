from __future__ import annotations

import uuid

import pytest

from backend.app import create_app


def test_record_visit_inserts_row(monkeypatch: pytest.MonkeyPatch, tmp_path):
    db_path = tmp_path / f"state-{uuid.uuid4().hex}.sqlite3"
    monkeypatch.setenv("APP_STATE_DB_PATH", str(db_path))
    app = create_app()
    client = app.test_client()

    shadow = app.config.get("SHADOW_INDEX_MANAGER")
    if shadow is not None:
        monkeypatch.setattr(shadow, "enqueue", lambda url: {"queued": url})

    response = client.post(
        "/api/visits", json={"url": "https://example.com", "enqueue": True}
    )
    assert response.status_code == 201
    payload = response.get_json()
    assert payload["ok"] is True
    if shadow is not None:
        assert payload["enqueue"]["queued"] == "https://example.com"

    state_db = app.config["APP_STATE_DB"]
    rows = state_db._conn.execute(
        "SELECT url FROM page_visits WHERE url=?", ("https://example.com",)
    ).fetchall()
    assert len(rows) == 1
