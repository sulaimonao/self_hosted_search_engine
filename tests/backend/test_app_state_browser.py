"""Unit tests for browser-focused helpers in :mod:`backend.app.db.store`."""

from __future__ import annotations

from datetime import datetime
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


def test_purge_history_domain_and_time_filters(tmp_path) -> None:
    state_db = _db(tmp_path)
    state_db.add_history_entry(tab_id="t1", url="https://alpha.example/a")
    mid = state_db.add_history_entry(tab_id="t1", url="https://beta.example/b")
    state_db.add_history_entry(tab_id="t1", url="https://alpha.example/c")
    deleted = state_db.purge_history(domain="alpha.example")
    assert deleted == 2
    remaining = state_db.query_history(limit=5)
    assert len(remaining) == 1 and remaining[0]["id"] == mid


def test_purge_history_clear_all_resets_tabs(tmp_path) -> None:
    state_db = _db(tmp_path)
    history_id = state_db.add_history_entry(tab_id="tab-keep", url="https://example.com")
    tab_record = state_db.get_tab("tab-keep")
    assert tab_record["current_history_id"] == history_id
    deleted = state_db.purge_history(clear_all=True)
    assert deleted == 1
    tab_record = state_db.get_tab("tab-keep")
    assert tab_record["current_history_id"] is None


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


def test_graph_site_overview_and_edges_filters(tmp_path) -> None:
    state_db = _db(tmp_path)
    # Seed pages across sites with topics and timestamps
    with state_db._lock, state_db._conn:  # type: ignore[attr-defined]
        state_db._conn.executemany(  # type: ignore[attr-defined]
            "INSERT INTO pages(url, site, title, last_seen, topics, embedding) VALUES(?, ?, ?, ?, ?, X'00')",
            [
                ("https://a.example/1", "a.example", "A1", "2025-01-10T00:00:00", "[\"ai\"]"),
                ("https://a.example/2", "a.example", "A2", "2025-01-11T00:00:00", "[\"ml\"]"),
                ("https://b.example/1", "b.example", "B1", "2025-01-12T00:00:00", "[\"ai\"]"),
                ("https://b.example/2", "b.example", "B2", "2025-02-01T00:00:00", "[\"chips\"]"),
                ("https://c.example/1", "c.example", "C1", "2025-03-01T00:00:00", "[\"ai\",\"chips\"]"),
            ],
        )
        state_db._conn.executemany(  # type: ignore[attr-defined]
            "INSERT OR IGNORE INTO link_edges(src_url, dst_url, relation) VALUES(?, ?, 'link')",
            [
                ("https://a.example/1", "https://b.example/1"),
                ("https://a.example/2", "https://b.example/2"),
                ("https://b.example/2", "https://c.example/1"),
                ("https://c.example/1", "https://a.example/1"),
                # intra-site edges (should still count for site degree but not cross-site weight)
                ("https://a.example/1", "https://a.example/2"),
            ],
        )

    # Site-level nodes aggregate correctly
    sites = state_db.graph_site_nodes(limit=10)
    site_map = {s["site"]: s for s in sites}
    assert set(site_map.keys()) == {"a.example", "b.example", "c.example"}
    assert site_map["a.example"]["pages"] == 2
    assert site_map["b.example"]["pages"] == 2
    assert site_map["c.example"]["pages"] == 1

    # Cross-site edges are aggregated with weights
    site_edges = state_db.graph_site_edges(limit=10, min_weight=1)
    # Expect at least three cross-site edges from the data above
    assert any(e["src_site"] == "a.example" and e["dst_site"] == "b.example" for e in site_edges)
    assert any(e["src_site"] == "b.example" and e["dst_site"] == "c.example" for e in site_edges)
    assert any(e["src_site"] == "c.example" and e["dst_site"] == "a.example" for e in site_edges)

    # Page-level edges filtering by category and date
    filtered_edges = state_db.graph_edges(
        limit=50,
        category="ai",
        start=datetime.fromisoformat("2025-01-01T00:00:00"),
        end=datetime.fromisoformat("2025-12-31T23:59:59"),
    )
    assert filtered_edges  # edges connecting pages with 'ai' topics within date range

    # Filtering by site should constrain edges
    a_edges = state_db.graph_edges(site="a.example", limit=50)
    assert a_edges and all(
        e["src_url"].startswith("https://a.example/") or e["dst_url"].startswith("https://a.example/") for e in a_edges
    )
