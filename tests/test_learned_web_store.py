from __future__ import annotations

import json
import sqlite3

from backend.app.search.learned_web import LearnedWebStore


def test_learned_web_returns_empty_when_db_missing(tmp_path):
    store = LearnedWebStore(tmp_path / "missing.sqlite3")
    results = store.similar_urls("python packaging", limit=5, min_similarity=0.2)
    assert results == []


def test_learned_web_similarity_and_limit(tmp_path):
    db_path = tmp_path / "learned.sqlite3"
    store = LearnedWebStore(db_path)

    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE discoveries (
            id INTEGER PRIMARY KEY,
            url TEXT NOT NULL,
            embedding TEXT NOT NULL,
            updated_at REAL DEFAULT (strftime('%s','now'))
        )
        """
    )
    conn.executemany(
        "INSERT INTO discoveries (url, embedding, updated_at) VALUES (?, ?, ?)",
        [
            (
                "https://example.com/pkg-guide",
                json.dumps(store.embed("python packaging guide")),
                200.0,
            ),
            (
                "https://example.com/python-intro",
                json.dumps(store.embed("introduction to python")),
                150.0,
            ),
            (
                "https://example.com/gardening",
                json.dumps(store.embed("gardening tips")),
                300.0,
            ),
        ],
    )
    conn.commit()
    conn.close()

    results = store.similar_urls("python packaging", limit=2, min_similarity=0.1)
    assert results[0] == "https://example.com/pkg-guide"
    assert "https://example.com/gardening" not in results
    assert len(results) == 2
