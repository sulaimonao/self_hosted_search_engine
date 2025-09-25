from __future__ import annotations

import sqlite3

from backend.agent.frontier_store import FrontierStore


def test_enqueue_dedupe(tmp_path):
    store = FrontierStore(tmp_path / "frontier.sqlite3")
    assert store.enqueue("https://example.com/a", topic="alpha", reason="initial") is True
    assert store.enqueue("https://example.com/a", topic="alpha", reason="update") is True
    with sqlite3.connect(store.path) as conn:
        reason, topic = conn.execute(
            "SELECT reason, topic FROM frontier_queue WHERE url=?", ("https://example.com/a",)
        ).fetchone()
    assert reason == "update"
    assert topic == "alpha"
    stats = store.stats()
    assert stats.queued == 1
