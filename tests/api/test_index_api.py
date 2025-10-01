from __future__ import annotations

import uuid

from backend.app import create_app


def test_index_upsert_and_search(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    chroma_dir = tmp_path / "chroma"
    chroma_db = tmp_path / "index.duckdb"

    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("CHROMA_PERSIST_DIR", str(chroma_dir))
    monkeypatch.setenv("CHROMA_DB_PATH", str(chroma_db))
    monkeypatch.setenv("EMBED_TEST_MODE", "1")
    monkeypatch.setenv("FOCUSED_CRAWL_ENABLED", "0")
    monkeypatch.setenv("LLM_EMBEDDER", "embeddinggemma")

    app = create_app()
    app.testing = True
    client = app.test_client()

    doc_id = uuid.uuid4().hex
    upsert_payload = {
        "url": f"https://example.com/{doc_id}",
        "title": "Example Document",
        "text": "Self-hosted search indexing relies on embeddinggemma vectors.",
    }

    upsert_response = client.post("/api/index/upsert", json=upsert_payload)
    assert upsert_response.status_code == 200
    upsert_data = upsert_response.get_json()
    assert upsert_data["chunks"] > 0
    assert upsert_data["dims"] == 128

    search_response = client.post(
        "/api/index/search",
        json={"query": "embeddinggemma vectors", "k": 3},
    )
    assert search_response.status_code == 200
    results = search_response.get_json().get("results")
    assert results, "expected at least one vector search result"
    assert any("embeddinggemma" in hit.get("chunk", "") for hit in results)
