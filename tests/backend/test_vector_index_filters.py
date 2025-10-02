from __future__ import annotations

from backend.app.config import AppConfig
from backend.app.services.vector_index import VectorIndexService
from engine.config import (
    CrawlConfig,
    EngineConfig,
    IndexConfig,
    ModelConfig,
    OllamaConfig,
    RetrievalConfig,
)


def _build_engine_config(tmp_path):
    persist_dir = tmp_path / "chroma"
    db_path = tmp_path / "index.duckdb"
    persist_dir.mkdir(parents=True, exist_ok=True)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return EngineConfig(
        models=ModelConfig(
            llm_primary="gpt-oss",
            llm_fallback=None,
            embed="embeddinggemma",
        ),
        ollama=OllamaConfig(base_url="http://127.0.0.1:11434"),
        retrieval=RetrievalConfig(k=5, min_hits=1, similarity_threshold=0.0),
        index=IndexConfig(persist_dir=persist_dir, db_path=db_path),
        crawl=CrawlConfig(
            user_agent="test",
            request_timeout=1,
            read_timeout=1,
            max_pages=1,
            sleep_seconds=0.0,
        ),
    )


def test_vector_index_search_filters(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    chroma_dir = tmp_path / "chroma_store"
    duckdb_path = tmp_path / "index.duckdb"

    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("CHROMA_PERSIST_DIR", str(chroma_dir))
    monkeypatch.setenv("CHROMA_DB_PATH", str(duckdb_path))
    monkeypatch.setenv("EMBED_TEST_MODE", "1")
    monkeypatch.setenv("FOCUSED_CRAWL_ENABLED", "0")
    monkeypatch.setenv("LLM_EMBEDDER", "embeddinggemma")

    app_config = AppConfig.from_env()
    app_config.ensure_dirs()

    engine_config = _build_engine_config(tmp_path)
    service = VectorIndexService(engine_config=engine_config, app_config=app_config)

    service.upsert_document(
        text="alpha document about embeddings",
        url="https://example.com/a",
        title="Doc A",
        metadata={"category": "news", "year": 2024},
    )

    service.upsert_document(
        text="beta document covering embeddings",
        url="https://example.com/b",
        title="Doc B",
        metadata={"category": "blog", "year": 2023},
    )

    results_news = service.search(
        "alpha document",
        k=5,
        filters={"category": "news"},
    )
    assert {hit["url"] for hit in results_news} == {"https://example.com/a"}

    results_news_year = service.search(
        "alpha document",
        k=5,
        filters={"category": "news", "year": 2024},
    )
    assert {hit["url"] for hit in results_news_year} == {"https://example.com/a"}

    results_blog = service.search(
        "alpha document",
        k=5,
        filters={"category": "blog"},
    )
    assert {hit["url"] for hit in results_blog} == {"https://example.com/b"}

    results_mismatch = service.search(
        "alpha document",
        k=5,
        filters={"category": "news", "year": 2023},
    )
    assert results_mismatch == []

    results_with_none = service.search(
        "alpha document",
        k=5,
        filters={"category": "news", "unused": None},
    )
    assert {hit["url"] for hit in results_with_none} == {"https://example.com/a"}
