"""Token aware text chunker."""

from __future__ import annotations

from dataclasses import dataclass

import tiktoken


@dataclass(slots=True)
class Chunk:
    """Represents a chunk of text with token-level metadata."""

    text: str
    start: int
    end: int
    token_count: int


class TokenChunker:
    """Splits text into overlapping token windows suitable for embeddings."""

    def __init__(
        self,
        encoding_name: str = "cl100k_base",
        chunk_size: int = 400,
        overlap: int = 40,
    ) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if overlap < 0:
            raise ValueError("overlap must be >= 0")
        self.chunk_size = chunk_size
        self.overlap = overlap
        self._encoding = self._load_encoding(encoding_name)

    @staticmethod
    def _load_encoding(name: str) -> tiktoken.Encoding:
        try:
            return tiktoken.get_encoding(name)
        except KeyError:  # pragma: no cover - fallback for unsupported encoding names
            return tiktoken.get_encoding("cl100k_base")

    def chunk_text(self, text: str) -> list[Chunk]:
        text = text.strip()
        if not text:
            return []
        token_ids = self._encoding.encode(text)
        total_tokens = len(token_ids)
        if total_tokens == 0:
            return []

        chunks: list[Chunk] = []
        start_token = 0
        prefix_text = ""
        while start_token < total_tokens:
            end_token = min(start_token + self.chunk_size, total_tokens)
            chunk_tokens = token_ids[start_token:end_token]
            chunk_text = self._encoding.decode(chunk_tokens)
            chunk_text_stripped = chunk_text.strip()
            start_char = len(prefix_text)
            end_char = start_char + len(chunk_text)
            if chunk_text_stripped:
                chunks.append(
                    Chunk(
                        text=chunk_text_stripped,
                        start=start_char,
                        end=end_char,
                        token_count=len(chunk_tokens),
                    )
                )
            if end_token >= total_tokens:
                break
            start_token = max(0, end_token - self.overlap)
            prefix_text = self._encoding.decode(token_ids[:start_token])
        return chunks


__all__ = ["TokenChunker", "Chunk"]
