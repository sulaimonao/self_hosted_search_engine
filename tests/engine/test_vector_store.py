from __future__ import annotations

import hashlib
import json

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


class RecordingCollection:
    def __init__(self) -> None:
        self.deleted: list[dict] = []
        self.add_calls: list[dict] = []

    def delete(self, where=None, **kwargs):  # pragma: no cover - signature compatibility
        self.deleted.append({"where": where, **kwargs})

    def add(self, *, ids, documents, metadatas, embeddings):
        self.add_calls.append(
            {
                "ids": ids,
                "documents": documents,
                "metadatas": metadatas,
                "embeddings": embeddings,
            }
        )


def test_upsert_sanitizes_metadata(tmp_path):
    persist_dir = tmp_path / "chroma"
    db_path = tmp_path / "index.duckdb"
    store = VectorStore(persist_dir, db_path)

    recording = RecordingCollection()
    store._collection = recording  # type: ignore[attr-defined]

    url = "https://example.com/article"
    title = "Example"
    etag = None
    content = "Chunk with complex metadata"
    content_hash = _hash(content)

    chunk = Chunk(text=content, start=0, end=len(content), token_count=["tok", "tok2"])  # type: ignore[arg-type]
    embedding = [0.4, 0.5, 0.6]

    store.upsert(url, title, etag, content_hash, [chunk], [embedding])

    assert recording.deleted[0]["where"] == {"url": url}
    assert len(recording.add_calls) == 1
    metadata = recording.add_calls[0]["metadatas"][0]
    assert "etag" not in metadata
    assert metadata["token_count"] == json.dumps(["tok", "tok2"], ensure_ascii=False)
