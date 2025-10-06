import time

import pytest

from backend.app.config import AppConfig
from backend.app.db import AppStateDB
from backend.app.services.vector_index import EmbedderUnavailableError, VectorIndexService
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
        models=ModelConfig(llm_primary="gpt-oss", llm_fallback=None, embed="embeddinggemma"),
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


@pytest.fixture()
def vector_service(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    chroma_dir = tmp_path / "chroma_store"
    duckdb_path = tmp_path / "index.duckdb"

    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("CHROMA_PERSIST_DIR", str(chroma_dir))
    monkeypatch.setenv("CHROMA_DB_PATH", str(duckdb_path))
    monkeypatch.setenv("FOCUSED_CRAWL_ENABLED", "0")
    monkeypatch.setenv("EMBED_TEST_MODE", "0")

    app_config = AppConfig.from_env()
    app_config.ensure_dirs()
    state_db = AppStateDB(app_config.app_state_db_path)

    engine_config = _build_engine_config(tmp_path)
    service = VectorIndexService(engine_config=engine_config, app_config=app_config, state_db=state_db)
    return service, state_db


def test_embed_with_retry_attempts(monkeypatch, vector_service):
    service, _ = vector_service
    attempts: list[int] = []

    def fake_embed(texts):
        attempts.append(len(texts))
        raise EmbedderUnavailableError(service._embed_model, detail="warming")

    monkeypatch.setattr(service, "_embed_documents", fake_embed)
    monkeypatch.setattr(service, "_ensure_embedder_ready", lambda **_kwargs: None)
    monkeypatch.setattr(time, "sleep", lambda _: None)

    with pytest.raises(EmbedderUnavailableError):
        service._embed_with_retry(["hello"], attempts=3, initial_delay=0.0)

    assert len(attempts) == 3


def test_upsert_document_queues_pending(vector_service, monkeypatch):
    service, state_db = vector_service

    def fake_embed(texts):
        raise EmbedderUnavailableError(service._embed_model, detail="warming")

    monkeypatch.setattr(service, "_embed_documents", fake_embed)
    monkeypatch.setattr(service, "_ensure_embedder_ready", lambda **_kwargs: None)
    monkeypatch.setattr(time, "sleep", lambda _: None)

    result = service.upsert_document(text="Example document body", url="https://example.com", title="Example")
    assert result.chunks == 0

    now = time.time()
    monkeypatch.setattr(time, "time", lambda: now + 10)
    pending = state_db.pop_pending_documents()
    assert pending, "expected pending vector records"
    record = pending[0]
    assert record["doc_id"]
    assert record["chunks"]
    assert record["sim_signature"] is not None
