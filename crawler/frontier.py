"""Focused crawl frontier helpers."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree

LOGGER = logging.getLogger(__name__)

PATTERN_BANK = [
    "/docs/",
    "/kb/",
    "/handbook/",
    "/guides/",
    "/manual/",
    "/whitepaper/",
    "/cookbook/",
    "/blog/",
]
SITEMAP_CANDIDATES = [
    "sitemap.xml",
    "sitemap_index.xml",
    "sitemap/sitemap.xml",
]
DEFAULT_COOLDOWN = max(0, int(os.getenv("SMART_TRIGGER_COOLDOWN", "900")))


@dataclass
class Candidate:
    url: str
    source: str
    weight: float


class CrawlCooldowns:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.data = self._load()

    def _load(self) -> Dict[str, float]:
        if not self.path.exists():
            return {}
        try:
            raw = json.loads(self.path.read_text("utf-8"))
        except Exception:
            return {}
        return {str(k): float(v) for k, v in raw.items() if isinstance(k, str)}

    def allowed(self, query: str, domain: str, cooldown: int, now: float) -> bool:
        if cooldown <= 0:
            return True
        key = self._key(query, domain)
        last = self.data.get(key)
        if last is None:
            return True
        return (now - last) >= cooldown

    def mark(self, query: str, domain: str, timestamp: float) -> None:
        key = self._key(query, domain)
        self.data[key] = float(timestamp)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2, sort_keys=True), encoding="utf-8")

    @staticmethod
    def _key(query: str, domain: str) -> str:
        digest = hashlib.sha1(query.lower().encode("utf-8")).hexdigest()[:16]
        return f"{digest}|{domain.lower()}"


def _sanitize(url: str) -> Optional[str]:
    candidate = (url or "").strip()
    if not candidate:
        return None
    if not candidate.startswith(("http://", "https://")):
        candidate = "https://" + candidate.lstrip("/")
    parsed = urlparse(candidate)
    if not parsed.scheme or not parsed.netloc:
        return None
    scheme = parsed.scheme if parsed.scheme in {"http", "https"} else "https"
    path = parsed.path or "/"
    return f"{scheme}://{parsed.netloc}{path}"


def _keywords(query: str) -> List[str]:
    words = re.findall(r"[a-z0-9]+", query.lower())
    stopwords = {"a", "an", "and", "for", "from", "how", "in", "of", "on", "or", "the", "to", "what", "where", "why"}
    filtered = [word for word in words if word not in stopwords]
    return filtered or words


def _domain_candidates(domain: str, query: str) -> Iterable[str]:
    base = domain.rstrip("/")
    if not base.startswith("http"):
        base = "https://" + base
    yield base
    for pattern in PATTERN_BANK:
        yield base + pattern
    encoded = query.replace(" ", "+")
    yield base + f"/search?q={encoded}"


def _query_candidates(query: str) -> Iterable[str]:
    keywords = _keywords(query)
    if not keywords:
        return []
    base = keywords[0]
    slug = "-".join(keywords[:3])
    tlds = ["com", "org", "io", "dev", "net"]
    suggestions: List[str] = []
    for tld in tlds:
        suggestions.append(f"https://{base}.{tld}")
        suggestions.append(f"https://docs.{base}.{tld}")
        suggestions.append(f"https://{base}.{tld}/docs")
        suggestions.append(f"https://{base}.{tld}/blog")
    if slug:
        suggestions.append(f"https://{slug}.com")
        suggestions.append(f"https://{slug}.io")
    suggestions.append(f"https://{base}.readthedocs.io/en/latest")
    suggestions.append(f"https://{base}.github.io")
    suggestions.append(f"https://{base}.gitbook.io")
    return suggestions


def build_frontier(
    query: str,
    *,
    extra_urls: Optional[Sequence[str]] = None,
    seed_domains: Optional[Sequence[str]] = None,
    budget: int = 10,
    cooldowns: Optional[CrawlCooldowns] = None,
    cooldown_seconds: Optional[int] = None,
    now: Optional[float] = None,
) -> List[Candidate]:
    q = (query or "").strip()
    if not q:
        return []
    limit = max(1, int(budget))
    collection: Dict[str, Candidate] = {}
    current_time = now or time.time()
    cooldown_value = DEFAULT_COOLDOWN if cooldown_seconds is None else max(0, int(cooldown_seconds))

    def _add(url: str, source: str, weight: float) -> None:
        sanitized = _sanitize(url)
        if not sanitized:
            return
        domain = urlparse(sanitized).netloc.lower()
        if cooldowns and not cooldowns.allowed(q, domain, cooldown_value, current_time):
            LOGGER.debug("skipping %s due to cooldown", sanitized)
            return
        existing = collection.get(sanitized)
        if existing is None or weight > existing.weight:
            collection[sanitized] = Candidate(url=sanitized, source=source, weight=weight)

    for url in extra_urls or []:
        _add(url, source="llm", weight=1.5)
        if len(collection) >= limit:
            break

    if len(collection) < limit:
        for domain in seed_domains or []:
            for candidate in _domain_candidates(domain, q):
                _add(candidate, source="seed", weight=1.0)
                if len(collection) >= limit:
                    break
            if len(collection) >= limit:
                break

    if len(collection) < limit:
        for url in _query_candidates(q):
            _add(url, source="heuristic", weight=0.8)
            if len(collection) >= limit:
                break

    ordered = sorted(collection.values(), key=lambda item: item.weight, reverse=True)
    return ordered[:limit]


async def discover_sitemaps(client, base_url: str, limit: int = 20) -> List[str]:
    parsed = urlparse(base_url)
    if not parsed.scheme or not parsed.netloc:
        return []
    root = f"{parsed.scheme}://{parsed.netloc}/"
    discovered: List[str] = []
    for suffix in SITEMAP_CANDIDATES:
        url = urljoin(root, suffix)
        try:
            response = await client.get(url, timeout=5.0, follow_redirects=True)
        except Exception:
            continue
        if response.status_code >= 400 or "<html" in response.text.lower():
            continue
        try:
            tree = ElementTree.fromstring(response.text)
        except ElementTree.ParseError:
            continue
        for element in tree.iter():
            if element.tag.endswith("loc") and element.text:
                sanitized = _sanitize(element.text)
                if sanitized:
                    discovered.append(sanitized)
                    if len(discovered) >= limit:
                        return discovered
    return discovered
