"""Host-level authority estimates derived from crawl outlinks."""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from collections.abc import Iterable
from typing import Mapping
from urllib.parse import urlparse

DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
DEFAULT_AUTHORITY_PATH = Path(os.getenv("AUTHORITY_PATH", DATA_DIR / "index" / "authority.json"))


def _normalize_host(value: str) -> str | None:
    if not value:
        return None
    parsed = urlparse(value)
    host = parsed.netloc or value
    host = host.lower().strip()
    if not host:
        return None
    return host[4:] if host.startswith("www.") else host


@dataclass(slots=True)
class AuthorityIndex:
    scores: dict[str, int] = field(default_factory=dict)
    path: Path = field(default=DEFAULT_AUTHORITY_PATH)

    @classmethod
    def load(cls, path: Path) -> "AuthorityIndex":
        try:
            payload = json.loads(path.read_text("utf-8"))
        except FileNotFoundError:
            payload = {}
        except json.JSONDecodeError:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        data = {str(host): int(value) for host, value in payload.items() if isinstance(host, str)}
        return cls(scores=data, path=path)

    @classmethod
    def load_default(cls) -> "AuthorityIndex":
        return cls.load(DEFAULT_AUTHORITY_PATH)

    def score_for(self, url_or_host: str) -> float:
        host = _normalize_host(url_or_host)
        if not host:
            return 0.0
        count = max(0, self.scores.get(host, 0))
        return round(math.log1p(count), 3)

    def update_from_docs(self, docs: Iterable[Mapping[str, object]]) -> None:
        for doc in docs:
            url = doc.get("url")
            host = _normalize_host(str(url))
            if not host:
                continue
            self.scores.setdefault(host, 0)
            outlinks = doc.get("outlinks") or []
            if isinstance(outlinks, str):  # defensive: allow comma separated
                outlinks = [item.strip() for item in outlinks.split(",") if item.strip()]
            if not isinstance(outlinks, Iterable):
                continue
            seen: set[str] = set()
            for link in outlinks:
                normalized = _normalize_host(str(link))
                if not normalized or normalized == host:
                    continue
                if normalized in seen:
                    continue
                self.scores[normalized] = self.scores.get(normalized, 0) + 1
                seen.add(normalized)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        serializable = {host: count for host, count in sorted(self.scores.items())}
        self.path.write_text(json.dumps(serializable, indent=2, sort_keys=True), encoding="utf-8")


__all__ = ["AuthorityIndex"]
