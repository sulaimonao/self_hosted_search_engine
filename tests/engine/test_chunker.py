"""Tests for the token chunker configuration validation."""

from __future__ import annotations

import pytest

from engine.indexing.chunk import TokenChunker


def test_chunker_rejects_overlap_larger_or_equal_to_chunk_size() -> None:
    with pytest.raises(ValueError, match="overlap must be smaller than chunk_size"):
        TokenChunker(chunk_size=10, overlap=10)

    with pytest.raises(ValueError, match="overlap must be smaller than chunk_size"):
        TokenChunker(chunk_size=10, overlap=12)


def test_chunker_accepts_smaller_overlap() -> None:
    chunker = TokenChunker(chunk_size=10, overlap=0)
    chunks = chunker.chunk_text("hello world")
    assert chunks, "Expected chunker to produce at least one chunk"
