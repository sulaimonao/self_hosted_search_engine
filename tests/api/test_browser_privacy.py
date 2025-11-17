from __future__ import annotations

from pathlib import Path

import pytest

from backend.app import create_app


@pytest.fixture()
def browser_app(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    db_path = tmp_path / "state.sqlite3"
    monkeypatch.setenv("APP_STATE_DB_PATH", str(db_path))
    app = create_app()
    return app


def test_delete_history_requires_filter(browser_app):
    client = browser_app.test_client()
    response = client.delete("/api/browser/history")
    assert response.status_code == 400
    payload = response.get_json()
    assert payload == {
        "ok": False,
        "error": {
            "code": "FILTER_REQUIRED",
            "message": "clear_all or a domain/time filter is required",
            "details": {},
        },
    }


def test_delete_history_domain_filter(browser_app):
    state_db = browser_app.config["APP_STATE_DB"]
    state_db.add_history_entry(tab_id="t1", url="https://example.com/a")
    state_db.add_history_entry(tab_id="t1", url="https://other.com/a")
    client = browser_app.test_client()
    response = client.delete(
        "/api/browser/history",
        json={"domain": "example.com"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["data"]["deleted_count"] == 1
    assert payload["data"]["filters"]["domain"] == "example.com"
    urls = [row["url"] for row in state_db.query_history(limit=10)]
    assert urls == ["https://other.com/a"]


def test_delete_history_clear_all_resets_tabs(browser_app):
    state_db = browser_app.config["APP_STATE_DB"]
    history_id = state_db.add_history_entry(tab_id="tab-clear", url="https://example.com")
    tab_record = state_db.get_tab("tab-clear")
    assert tab_record["current_history_id"] == history_id
    client = browser_app.test_client()
    response = client.delete(
        "/api/browser/history",
        json={"clear_all": True},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["data"]["deleted_count"] == 1
    assert payload["data"]["filters"]["clear_all"] is True
    tab_record = state_db.get_tab("tab-clear")
    assert tab_record["current_history_id"] is None
