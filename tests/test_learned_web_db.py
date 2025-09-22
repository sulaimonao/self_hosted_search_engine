from __future__ import annotations

import sqlite3

from frontier.dedupe import ContentFingerprint

from backend.app.search.embedding import embed_query
from server.learned_web_db import LearnedWebDB


def test_learned_web_db_persists_discovery_and_pages(tmp_path) -> None:
    db_path = tmp_path / "learned.sqlite3"
    db = LearnedWebDB(db_path)

    assert db.domain_value_map() == {}

    domain_info = db.record_discovery(
        "test query",
        "https://example.com/docs",
        reason="frontier",
        score=1.2,
        source="seed",
        discovered_at=123.0,
    )
    assert domain_info is not None
    domain_id, created = domain_info
    assert created is True

    value_map = db.domain_value_map()
    assert value_map["example.com"] >= 1.2

    crawl_id = db.start_crawl(
        "test query",
        started_at=200.0,
        budget=5,
        seed_count=3,
        use_llm=True,
        model="mini",
    )

    fingerprint = ContentFingerprint(simhash=42, md5="abc123")
    page_id = db.record_page(
        crawl_id,
        url="https://example.com/docs",
        status=200,
        title="Docs",
        fetched_at=201.0,
        fingerprint_simhash=fingerprint.simhash,
        fingerprint_md5=fingerprint.md5,
    )
    assert page_id is not None

    db.record_links(
        page_id,
        ["https://example.com/blog", "https://other.dev/guide"],
        discovered_at=202.0,
        crawl_id=crawl_id,
    )

    db.mark_pages_indexed(["https://example.com/docs"], indexed_at=203.0)
    db.complete_crawl(crawl_id, completed_at=204.0, pages_fetched=1, docs_indexed=1, raw_path="/tmp/raw.json")

    reopened = LearnedWebDB(db_path)
    top = reopened.top_domains(5)
    assert "example.com" in top

    with sqlite3.connect(db_path) as conn:
        discovery_count = conn.execute(
            "SELECT discovery_count FROM domains WHERE host = ?",
            ("example.com",),
        ).fetchone()
        assert discovery_count and discovery_count[0] >= 1

        indexed_at = conn.execute(
            "SELECT indexed_at FROM pages WHERE url = ?",
            ("https://example.com/docs",),
        ).fetchone()
        assert indexed_at and indexed_at[0] >= 203.0

        link_count = conn.execute("SELECT COUNT(*) FROM links").fetchone()
        assert link_count and link_count[0] >= 2


def test_similar_discovery_seeds(tmp_path) -> None:
    db_path = tmp_path / "learned.sqlite3"
    db = LearnedWebDB(db_path)

    query_a = "python packaging"
    query_b = "python virtualenv"
    embed_a = embed_query(query_a)
    embed_b = embed_query(query_b)
    db.upsert_query_embedding(query_a, embed_a)
    db.upsert_query_embedding(query_b, embed_b)
    db.record_discovery(query_a, "https://packaging.python.org", reason="frontier", score=1.0)
    db.record_discovery(query_a, "https://pypi.org/project/pip", reason="frontier", score=0.8)
    db.record_discovery(query_b, "https://virtualenv.pypa.io", reason="frontier", score=0.9)

    probe = embed_query("python package manager")
    seeds = db.similar_discovery_seeds(probe, limit=3, min_similarity=0.1)

    assert "https://packaging.python.org" in seeds
    assert len(seeds) >= 1
