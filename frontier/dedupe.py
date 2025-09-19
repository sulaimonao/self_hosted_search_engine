"""Deduplication helpers for crawl frontiers."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Iterable


def _optimal_bloom_params(capacity: int, error_rate: float) -> tuple[int, int]:
    m = int(-(capacity * math.log(error_rate)) / (math.log(2) ** 2))
    m = max(8, m)
    k = int((m / capacity) * math.log(2)) if capacity else 1
    k = max(1, k)
    return m, k


class UrlBloom:
    """Simple Bloom filter tuned for thousands of URLs."""

    def __init__(self, capacity: int = 10_000, error_rate: float = 0.01) -> None:
        m, k = _optimal_bloom_params(capacity, error_rate)
        self._bits = bytearray(math.ceil(m / 8))
        self._size = m
        self._hashes = k

    def _positions(self, value: str) -> Iterable[int]:
        payload = value.encode("utf-8", errors="ignore")
        digest1 = hashlib.sha1(payload).digest()
        digest2 = hashlib.md5(payload).digest()
        for i in range(self._hashes):
            combined = int.from_bytes(digest1[i : i + 4], "big", signed=False)
            fallback = int.from_bytes(digest2[i : i + 4], "big", signed=False)
            yield (combined ^ fallback) % self._size

    def add(self, value: str) -> None:
        for position in self._positions(value):
            byte_index = position // 8
            bit_index = position % 8
            self._bits[byte_index] |= 1 << bit_index

    def __contains__(self, value: str) -> bool:
        for position in self._positions(value):
            byte_index = position // 8
            bit_index = position % 8
            if not (self._bits[byte_index] & (1 << bit_index)):
                return False
        return True


def _tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    current = []
    for char in text.lower():
        if char.isalnum():
            current.append(char)
        else:
            if current:
                tokens.append("".join(current))
                current = []
    if current:
        tokens.append("".join(current))
    return tokens


def _simhash(text: str) -> int:
    weights = [0] * 64
    for token in _tokenize(text):
        token_hash = int.from_bytes(hashlib.sha1(token.encode("utf-8")).digest()[:8], "big")
        for bit in range(64):
            if token_hash & (1 << bit):
                weights[bit] += 1
            else:
                weights[bit] -= 1
    fingerprint = 0
    for bit, weight in enumerate(weights):
        if weight > 0:
            fingerprint |= 1 << bit
    return fingerprint


@dataclass(slots=True)
class ContentFingerprint:
    """Lightweight content fingerprint combining SimHash + MD5."""

    simhash: int
    md5: str

    @classmethod
    def from_text(cls, text: str) -> "ContentFingerprint":
        normalized = text or ""
        return cls(simhash=_simhash(normalized), md5=hashlib.md5(normalized.encode("utf-8")).hexdigest())


__all__ = ["ContentFingerprint", "UrlBloom"]
