from __future__ import annotations

import uuid

import pytest

from backend.app import create_app


def test_docs_listing_and_detail(monkeypatch: pytest.MonkeyPatch, tmp_path):
    db_path = tmp_path / f"state-{uuid.uuid4().hex}.sqlite3"
    monkeypatch.setenv("APP_STATE_DB_PATH", str(db_path))
    app = create_app()
    client = app.test_client()
    state_db = app.config["APP_STATE_DB"]

    state_db.record_crawl_job("job-1", query="test", normalized_path="/tmp/normalized.jsonl")
    state_db.update_crawl_status("job-1", "success")
    state_db.upsert_document(
        job_id="job-1",
        document_id="doc-1",
        url="https://example.com/page",
        canonical_url="https://example.com/page",
        site="example.com",
        title="Example Page",
        description="Sample description",
        language="en",
        fetched_at=0.0,
        normalized_path="/tmp/normalized.jsonl",
        text_len=120,
        tokens=24,
        content_hash="hash",
        categories=["test"],
        labels=["general"],
        source="test",
        verification={"hash": "hash"},
    )

    list_response = client.get("/api/docs", query_string={"query": "example.com"})
    assert list_response.status_code == 200
    items = list_response.get_json()["items"]
    assert any(item["id"] == "doc-1" for item in items)

    detail_response = client.get("/api/docs/doc-1")
    assert detail_response.status_code == 200
    detail = detail_response.get_json()["item"]
    assert detail["url"] == "https://example.com/page"
    assert detail["categories"] == ["test"]
    assert detail["labels"] == ["general"]
