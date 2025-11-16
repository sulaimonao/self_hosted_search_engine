import uuid
from pathlib import Path

from flask import Flask

from backend.app.api import browser as browser_api
from backend.app.db.store import AppStateDB


def make_app(tmp_path: Path) -> tuple[Flask, AppStateDB]:
    app = Flask(__name__)
    state_db = AppStateDB(tmp_path / f"state-{uuid.uuid4().hex}.sqlite3")
    app.config["APP_STATE_DB"] = state_db
    app.register_blueprint(browser_api.bp)
    return app, state_db


def test_history_updates_tab_and_thread_binding(tmp_path):
    app, state_db = make_app(tmp_path)
    client = app.test_client()

    resp = client.post(
        "/api/browser/history",
        json={"tab_id": "tab-1", "url": "https://example.com", "title": "Example"},
    )
    assert resp.status_code == 201

    tabs_resp = client.get("/api/browser/tabs")
    assert tabs_resp.status_code == 200
    tabs = tabs_resp.get_json()["items"]
    assert any(tab["id"] == "tab-1" and tab["current_url"] == "https://example.com" for tab in tabs)

    bind_resp = client.post(
        "/api/browser/tabs/tab-1/thread",
        json={"title": "Browser chat"},
    )
    assert bind_resp.status_code == 200
    payload = bind_resp.get_json()
    thread_id = payload["thread_id"]
    assert payload["tab"]["thread_id"] == thread_id

    detail_resp = client.get("/api/browser/tabs/tab-1")
    assert detail_resp.status_code == 200
    detail = detail_resp.get_json()["tab"]
    assert detail["thread_id"] == thread_id
    assert state_db.tab_thread_id("tab-1") == thread_id
