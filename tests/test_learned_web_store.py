from __future__ import annotations

import hashlib
import json
import math
import sqlite3

import pytest

from backend.app.search.learned_web import LearnedWebStore


def test_learned_web_returns_empty_when_db_missing(tmp_path):
    store = LearnedWebStore(tmp_path / "missing.sqlite3")
    results = store.similar_urls("python packaging", limit=5, min_similarity=0.2)
    assert results == []


def test_hashed_embedding_is_stable(tmp_path):
    store = LearnedWebStore(tmp_path / "unused.sqlite3", dimension=8)
    vector = store.embed("alpha beta alpha")

    assert len(vector) == 8

    bucket_alpha = int.from_bytes(hashlib.blake2b(b"alpha", digest_size=16).digest(), "big") % 8
    bucket_beta = int.from_bytes(hashlib.blake2b(b"beta", digest_size=16).digest(), "big") % 8

    expected = [0.0] * 8
    expected[bucket_alpha] = 2.0
    expected[bucket_beta] = 1.0
    norm = math.sqrt(sum(component * component for component in expected))
    expected = [component / norm for component in expected]

    assert vector == pytest.approx(expected)


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
