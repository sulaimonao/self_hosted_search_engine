"""Near-duplicate detection utilities using SimHash."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable

_WORD_RE = re.compile(r"[\w]+", re.UNICODE)


def tokenize(text: str) -> Iterable[str]:
    for match in _WORD_RE.finditer(text.lower()):
        token = match.group(0)
        if token:
            yield token


def simhash64(text: str) -> int:
    tokens = list(tokenize(text))
    if not tokens:
        return 0
    vector = [0] * 64
    for token in tokens:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        value = int.from_bytes(digest, "big", signed=False)
        for bit in range(64):
            if value & (1 << bit):
                vector[bit] += 1
            else:
                vector[bit] -= 1
    result = 0
    for bit, weight in enumerate(vector):
        if weight >= 0:
            result |= 1 << bit
    return result


def hamming_distance(a: int, b: int) -> int:
    return (a ^ b).bit_count()


@dataclass
class SimHashIndex:
    entries: Dict[str, int]

    @classmethod
    def load(cls, path: Path) -> "SimHashIndex":
        if not path.exists():
            return cls(entries={})
        try:
            data = json.loads(path.read_text("utf-8"))
        except Exception:
            return cls(entries={})
        if not isinstance(data, dict):
            return cls(entries={})
        casted = {}
        for url, value in data.items():
            try:
                casted[str(url)] = int(value)
            except Exception:
                continue
        return cls(entries=casted)

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.entries, indent=2, sort_keys=True), encoding="utf-8")

    def nearest(self, target: int, threshold: int = 3) -> str | None:
        for url, value in self.entries.items():
            if hamming_distance(target, value) <= threshold:
                return url
        return None

    def update(self, url: str, value: int) -> None:
        self.entries[url] = value
