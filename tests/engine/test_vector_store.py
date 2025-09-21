from __future__ import annotations

import hashlib

from engine.data.store import RetrievedChunk, VectorStore
from engine.indexing.chunk import Chunk


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_vector_store_round_trip(tmp_path):
    persist_dir = tmp_path / "chroma"
    db_path = tmp_path / "index.duckdb"
    store = VectorStore(persist_dir, db_path)

    url = "https://example.com/article"
    title = "Example"
    etag = "W/\"12345\""
    content = "This is a retrieved chunk"
    content_hash = _hash(content)

    assert store.needs_update(url, etag, content_hash) is True

    chunk = Chunk(text=content, start=0, end=len(content), token_count=5)
    embedding = [0.1, 0.2, 0.3]
    store.upsert(url, title, etag, content_hash, [chunk], [embedding])

    assert store.needs_update(url, etag, content_hash) is False
    assert store.needs_update(url, None, content_hash) is False
    assert store.needs_update(url, etag, _hash(content + "!")) is True

    results = store.query(embedding, k=3, similarity_threshold=0.5)
    assert len(results) == 1
    retrieved = results[0]
    assert isinstance(retrieved, RetrievedChunk)
    assert retrieved.text == content
    assert retrieved.title == title
    assert retrieved.url == url
    assert retrieved.similarity >= 0.99
