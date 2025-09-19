"""Maintain a lightweight, append-only store of crawl seeds."""

from __future__ import annotations

import json
import os
import time
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Mapping, Optional
from urllib.parse import urlparse

DEFAULT_SEEDS_PATH = Path(os.getenv("SEEDS_PATH", "data/seeds.jsonl"))

__all__ = [
    "DEFAULT_SEEDS_PATH",
    "domain_from_url",
    "get_top_domains",
    "load_entries",
    "merge_curated_seeds",
    "record_domains",
]


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def load_entries(path: Optional[Path] = None) -> list[dict]:
    """Return every JSONL entry from the seed store.

    Invalid JSON lines are ignored to make the log resilient to manual edits.
    """

    seeds_path = path or DEFAULT_SEEDS_PATH
    if not seeds_path.exists():
        return []

    entries: list[dict] = []
    with seeds_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                entries.append(payload)
    return entries


def domain_from_url(url: str) -> Optional[str]:
    """Extract the hostname for a URL, normalized for comparisons."""

    if not url:
        return None
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    host = (parsed.netloc or "").strip().lower()
    if not host:
        return None
    if host.startswith("www."):
        host = host[4:]
    return host or None


def _domain_weight(entries: Iterable[dict]) -> dict[str, float]:
    scores: dict[str, float] = defaultdict(float)
    for entry in entries:
        domain = entry.get("domain")
        if not isinstance(domain, str):
            continue
        normalized = domain.strip().lower()
        if not normalized:
            continue
        if normalized.startswith("www."):
            normalized = normalized[4:]
        try:
            score = float(entry.get("score", 0.0))
        except (TypeError, ValueError):
            score = 0.0
        # Keep the maximum score per domain to favor recent high quality seeds.
        scores[normalized] = max(scores[normalized], score)
    return scores


def get_top_domains(limit: int = 20, path: Optional[Path] = None) -> list[str]:
    """Return the highest scoring domains recorded in the seed store."""

    limit = max(0, int(limit))
    if limit == 0:
        return []

    entries = load_entries(path=path)
    if not entries:
        return []

    scores = _domain_weight(entries)
    ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    return [domain for domain, _ in ordered[:limit]]


def record_domains(
    domains: Mapping[str, float],
    *,
    query: str,
    reason: str,
    path: Optional[Path] = None,
) -> None:
    """Append the provided domain scores to the JSONL seed store."""

    if not domains:
        return

    seeds_path = path or DEFAULT_SEEDS_PATH
    _ensure_parent(seeds_path)

    timestamp = time.time()
    safe_reason = reason or "focused-crawl"

    with seeds_path.open("a", encoding="utf-8") as handle:
        for domain, score in domains.items():
            if not isinstance(domain, str):
                continue
            normalized = domain.strip().lower()
            if not normalized:
                continue
            if normalized.startswith("www."):
                normalized = normalized[4:]
            try:
                numeric_score = float(score)
            except (TypeError, ValueError):
                numeric_score = 0.0
            entry = {
                "domain": normalized,
                "score": numeric_score,
                "reason": safe_reason,
                "query": query,
                "ts": timestamp,
            }
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def merge_curated_seeds(
    curated_path: Path, *, store_path: Optional[Path] = None, reason: str = "curated"
) -> int:
    """Merge curated seed domains into the append-only store.

    The curated file must be JSONL with at least ``url`` and ``value_prior`` keys.
    Returns the number of new seed entries written to the store.
    """

    if not curated_path.exists():
        return 0

    domains: dict[str, float] = {}
    with curated_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                continue
            url = payload.get("url")
            domain = domain_from_url(url) if isinstance(url, str) else None
            if not domain:
                continue
            try:
                value = float(payload.get("value_prior", 0.0))
            except (TypeError, ValueError):
                value = 0.0
            domains[domain] = max(domains.get(domain, 0.0), value)

    if not domains:
        return 0

    record_domains(domains, query="curated-seeds", reason=reason, path=store_path)
    return len(domains)
