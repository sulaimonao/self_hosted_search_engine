"""Tests for the token-aware chunker."""

from __future__ import annotations

from engine.indexing.chunk import TokenChunker


def test_chunker_generates_overlapping_chunks():
    chunker = TokenChunker(chunk_size=50, overlap=10)
    text = " ".join(str(i) for i in range(200))
    chunks = chunker.chunk_text(text)
    assert len(chunks) >= 3
    for chunk in chunks:
        assert chunk.text
        assert chunk.end > chunk.start
        assert chunk.token_count <= 50
    # Ensure overlap by checking that the second chunk begins before the first chunk ends.
    assert chunks[1].start <= chunks[0].end
