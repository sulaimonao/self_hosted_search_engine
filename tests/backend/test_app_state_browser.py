"""Unit tests for browser-focused helpers in :mod:`backend.app.db.store`."""

from __future__ import annotations

from backend.app.db import AppStateDB


def _db(tmp_path) -> AppStateDB:
    return AppStateDB(tmp_path / "state.sqlite3")


def test_history_roundtrip(tmp_path) -> None:
    state_db = _db(tmp_path)
    history_id = state_db.add_history_entry(tab_id="tab-1", url="https://example.com")
    rows = state_db.query_history(limit=5)
    assert rows and rows[0]["id"] == history_id
    state_db.delete_history_entry(history_id)
    assert state_db.query_history(limit=5) == []


def test_bookmarks_crud(tmp_path) -> None:
    state_db = _db(tmp_path)
    folder_id = state_db.create_bookmark_folder("Research")
    bookmark_id = state_db.add_bookmark(
        url="https://example.com/ai",
        title="AI Article",
        folder_id=folder_id,
        tags=["ai", "chips"],
    )
    folders = state_db.list_bookmark_folders()
    assert any(folder["id"] == folder_id for folder in folders)
    bookmarks = state_db.list_bookmarks(folder_id)
    assert bookmarks and bookmarks[0]["id"] == bookmark_id
    assert set(bookmarks[0]["tags"]) == {"ai", "chips"}


def test_seed_sources(tmp_path) -> None:
    state_db = _db(tmp_path)
    seeds = [
        {"category_key": "tech", "url": "https://example.com", "title": "Example"},
        {"category_key": "news", "url": "https://news.example.com", "title": "News"},
    ]
    count = state_db.bulk_upsert_seed_sources(seeds)
    assert count == 2
    urls = state_db.enabled_seed_urls(["tech"])
    assert "https://example.com" in urls


def test_shadow_settings_and_enqueue(tmp_path) -> None:
    state_db = _db(tmp_path)
    state_db.set_shadow_settings(enabled=True, mode="visited_only")
    assert state_db.get_shadow_settings()["enabled"] is True
    assert state_db.effective_shadow_mode(None) == "visited_only"
    job_id = state_db.enqueue_crawl_job(
        "https://crawl.example", priority=5, reason="test"
    )
    status = state_db.crawl_job_status(job_id)
    assert status and status["reason"] == "test"
    overview = state_db.crawl_overview()
    assert {"queued", "running", "done", "error"}.issuperset(overview.keys())


def test_graph_queries(tmp_path) -> None:
    state_db = _db(tmp_path)
    summary = state_db.graph_summary()
    assert summary["pages"] == 0
    nodes = state_db.graph_nodes(limit=5)
    assert nodes == []
    edges = state_db.graph_edges(limit=5)
    assert edges == []
