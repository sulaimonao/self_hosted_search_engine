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
from typing import TYPE_CHECKING, Callable, Dict, Iterable, List, Mapping, Optional, Sequence
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree

from server.learned_web_db import get_db

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
DEFAULT_PER_HOST = max(1, int(os.getenv("FRONTIER_PER_HOST", "3")))
DEFAULT_POLITENESS_DELAY = max(0.0, float(os.getenv("FRONTIER_POLITENESS_DELAY", "1.0")))
DEFAULT_RERANK_MARGIN = max(0.0, float(os.getenv("FRONTIER_RERANK_MARGIN", "0.15")))

if TYPE_CHECKING:  # pragma: no cover - typing helper only
    from server.discover import DiscoveryHit


@dataclass
class Candidate:
    url: str
    source: str
    weight: float
    available_at: float = 0.0
    score: float | None = None

    def priority(self) -> float:
        return self.score if self.score is not None else self.weight


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


def _normalize_host(value: str) -> Optional[str]:
    candidate = (value or "").strip()
    if not candidate:
        return None
    probe = candidate if candidate.startswith(("http://", "https://")) else f"https://{candidate}"
    parsed = urlparse(probe)
    host = parsed.netloc or parsed.path
    if not host:
        return None
    lowered = host.lower()
    return lowered[4:] if lowered.startswith("www.") else lowered


def build_frontier(
    query: str,
    *,
    extra_urls: Optional[Sequence[str]] = None,
    seed_domains: Optional[Sequence[str]] = None,
    budget: int = 10,
    cooldowns: Optional[CrawlCooldowns] = None,
    cooldown_seconds: Optional[int] = None,
    now: Optional[float] = None,
    value_overrides: Optional[Mapping[str, float]] = None,
    discovery_hints: Optional[Sequence["DiscoveryHit"]] = None,
    per_host_cap: Optional[int] = None,
    politeness_delay: Optional[float] = None,
    rerank_fn: Optional[Callable[[str, List[Candidate]], List[Candidate]]] = None,
    rerank_margin: Optional[float] = None,
) -> List[Candidate]:
    q = (query or "").strip()
    if not q:
        return []
    limit = max(1, int(budget))
    collection: Dict[str, Candidate] = {}
    current_time = time.time() if now is None else float(now)
    cooldown_value = DEFAULT_COOLDOWN if cooldown_seconds is None else max(0, int(cooldown_seconds))
    per_host_limit = DEFAULT_PER_HOST if per_host_cap is None else max(1, int(per_host_cap))
    delay = DEFAULT_POLITENESS_DELAY if politeness_delay is None else max(0.0, float(politeness_delay))
    rerank_window = DEFAULT_RERANK_MARGIN if rerank_margin is None else max(0.0, float(rerank_margin))

    override_map: Dict[str, float] = {}
    try:
        for domain, score in get_db().domain_value_map().items():
            try:
                numeric = float(score)
            except (TypeError, ValueError):
                continue
            override_map[domain] = max(override_map.get(domain, 0.0), numeric)
    except Exception:  # pragma: no cover - defensive logging only
        LOGGER.debug("failed to load learned domain priors", exc_info=True)
    for domain, score in (value_overrides or {}).items():
        normalized = _normalize_host(domain)
        if not normalized:
            continue
        try:
            numeric = float(score)
        except (TypeError, ValueError):
            continue
        override_map[normalized] = max(override_map.get(normalized, 0.0), numeric)

    def _add(url: str, source: str, weight: float, *, score: float | None = None, respect_override: bool = True) -> None:
        sanitized = _sanitize(url)
        if not sanitized:
            return
        domain = urlparse(sanitized).netloc.lower()
        normalized = domain[4:] if domain.startswith("www.") else domain
        adjusted_weight = weight
        if respect_override and normalized in override_map:
            adjusted_weight = max(adjusted_weight, override_map[normalized])
        if cooldowns and not cooldowns.allowed(q, domain, cooldown_value, current_time):
            LOGGER.debug("skipping %s due to cooldown", sanitized)
            return
        existing = collection.get(sanitized)
        priority = score if score is not None else max(adjusted_weight, override_map.get(normalized, adjusted_weight))
        if existing is None or priority > existing.priority():
            collection[sanitized] = Candidate(
                url=sanitized,
                source=source,
                weight=adjusted_weight,
                score=priority,
            )

    for hint in discovery_hints or []:
        url = getattr(hint, "url", None)
        if not isinstance(url, str):
            continue
        source = getattr(hint, "source", "discovery")
        score = getattr(hint, "score", None)
        boost = getattr(hint, "boost", 1.0)
        weight = float(score if score is not None else boost)
        _add(url, source=source, weight=weight, score=score if score is not None else weight, respect_override=False)

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

    ordered = sorted(collection.values(), key=lambda item: item.priority(), reverse=True)

    if rerank_fn and ordered:
        cutoff_index = min(len(ordered), limit) - 1
        cutoff_score = ordered[cutoff_index].priority()
        borderline = [candidate for candidate in ordered if candidate.priority() >= cutoff_score - rerank_window]
        if borderline:
            reranked = rerank_fn(q, list(borderline))
            if reranked:
                borderline_urls = {candidate.url for candidate in borderline}
                mapping = {candidate.url: candidate for candidate in ordered}
                seen: set[str] = set()
                reordered: List[Candidate] = []
                for candidate in reranked:
                    target = mapping.get(candidate.url)
                    if target and target.url in borderline_urls and target.url not in seen:
                        reordered.append(target)
                        seen.add(target.url)
                for candidate in borderline:
                    if candidate.url not in seen:
                        reordered.append(candidate)
                prefix = [candidate for candidate in ordered if candidate.url not in borderline_urls]
                ordered = prefix + reordered

    host_counts: Dict[str, int] = {}
    host_available: Dict[str, float] = {}
    final: List[Candidate] = []
    for candidate in ordered:
        host = urlparse(candidate.url).netloc.lower()
        count = host_counts.get(host, 0)
        if count >= per_host_limit:
            continue
        available_at = max(host_available.get(host, current_time), candidate.available_at)
        candidate.available_at = available_at
        host_counts[host] = count + 1
        host_available[host] = available_at + delay
        final.append(candidate)
        if len(final) >= limit:
            break

    return final


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
