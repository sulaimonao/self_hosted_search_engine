from backend.app.db.store import AppStateDB
from backend.app.services import browser_import


def test_chrome_history_entry_mapping():
    raw = {
        "url": "https://example.com",
        "title": "Example",
        "last_visit_time": 13217452800000000,
        "referringVisitUrl": "https://referrer.test",
        "mime_type": "text/html",
        "http_status": 200,
    }
    entry = browser_import.ChromeHistoryEntry.from_row(raw)
    record = entry.to_record()
    assert record["url"] == "https://example.com"
    assert record["title"] == "Example"
    assert "visited_at" in record
    assert record["referrer"] == "https://referrer.test"
    assert record["content_type"] == "text/html"
    assert record["status_code"] == 200


def test_import_chrome_history_entries(tmp_path):
    state_db = AppStateDB(tmp_path / "history.sqlite3")
    rows = [
        {"url": "https://example.com", "title": "One", "last_visit_time": 13217452800000000},
        {"url": "https://example.com/about", "title": "About", "last_visit_time": 13217452810000000},
    ]
    inserted = browser_import.import_chrome_history_entries(state_db, rows)
    assert inserted == 2
    history = state_db.query_history(limit=10)
    assert len(history) == 2
    browser_import.import_chrome_history_entries(state_db, rows)
    history_after = state_db.query_history(limit=10)
    assert len(history_after) == 2
