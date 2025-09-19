"""Generate ranked candidate URLs for focused crawling."""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence
from urllib.parse import quote, urlparse, urlunparse

from frontier.dedupe import UrlBloom
from rank.authority import AuthorityIndex

from . import seeds as seed_store

LOGGER = logging.getLogger(__name__)

DEFAULT_BUDGET = int(os.getenv("FOCUSED_CRAWL_BUDGET", "50"))
VALUE_WEIGHT = float(os.getenv("FRONTIER_W_VALUE", "0.5"))
FRESH_WEIGHT = float(os.getenv("FRONTIER_W_FRESH", "0.3"))
AUTH_WEIGHT = float(os.getenv("FRONTIER_W_AUTH", "0.2"))
DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
CURATED_PATH = DATA_DIR / "seeds" / "curated_seeds.jsonl"

_STOPWORDS = {
    "a",
    "an",
    "and",
    "for",
    "from",
    "how",
    "in",
    "of",
    "on",
    "or",
    "the",
    "to",
    "what",
    "where",
    "why",
}

_TLD_GUESSES = ["com", "org", "io", "dev", "net"]
_DOMAIN_PATHS = [
    "/",
    "/docs",
    "/documentation",
    "/doc",
    "/blog",
    "/kb",
    "/knowledge",
    "/support",
    "/help",
    "/learn",
]
_DOMAIN_PATHS_WITH_QUERY = [
    "/search?q={query}",
    "/docs/search?q={query}",
    "/documentation/search?q={query}",
]


@dataclass(frozen=True)
class Candidate:
    """Focused crawl candidate URL and its provenance."""

    url: str
    source: str
    weight: float = 1.0
    value_prior: float = 0.0
    freshness_hint: float = 0.0
    host_authority: float = 0.0

    @property
    def priority(self) -> float:
        return (
            self.weight
            + VALUE_WEIGHT * self.value_prior
            + FRESH_WEIGHT * self.freshness_hint
            + AUTH_WEIGHT * self.host_authority
        )


__all__ = ["Candidate", "DEFAULT_BUDGET", "build_frontier"]


def _sanitize_url(value: str) -> Optional[str]:
    candidate = (value or "").strip()
    if not candidate:
        return None

    if not candidate.startswith(("http://", "https://")):
        candidate = "https://" + candidate.lstrip("/")

    try:
        parsed = urlparse(candidate)
    except ValueError:
        return None

    if not parsed.netloc:
        return None

    scheme = parsed.scheme if parsed.scheme in {"http", "https"} else "https"
    netloc = parsed.netloc
    path = parsed.path or ""
    if path and not path.startswith("/"):
        path = "/" + path
    sanitized = urlunparse((scheme, netloc, path or "", "", parsed.query, parsed.fragment))
    return sanitized.rstrip("/") or None


def _keywords(query: str) -> List[str]:
    words = re.findall(r"[a-z0-9]+", query.lower())
    filtered = [word for word in words if word not in _STOPWORDS]
    if filtered:
        return filtered
    return words


def _domain_candidates(domain: str, query: str) -> Iterable[str]:
    encoded_query = quote(query)
    for path in _DOMAIN_PATHS:
        yield f"{domain}{path}" if domain.startswith("http") else f"https://{domain}{path}"
    for template in _DOMAIN_PATHS_WITH_QUERY:
        suffix = template.format(query=encoded_query)
        if domain.startswith("http"):
            yield f"{domain}{suffix}"
        else:
            yield f"https://{domain}{suffix}"


def _query_candidates(query: str) -> Iterable[str]:
    keywords = _keywords(query)
    if not keywords:
        return []

    base = keywords[0]
    slug = "-".join(keywords[:3])

    suggestions: list[str] = []
    for tld in _TLD_GUESSES:
        suggestions.append(f"https://{base}.{tld}")
        suggestions.append(f"https://docs.{base}.{tld}")
        suggestions.append(f"https://{base}.{tld}/docs")
        suggestions.append(f"https://{base}.{tld}/documentation")
    if slug:
        suggestions.append(f"https://{slug}.com")
        suggestions.append(f"https://{slug}.io")
    suggestions.append(f"https://{base}.readthedocs.io/en/latest")
    suggestions.append(f"https://{base}.github.io")
    suggestions.append(f"https://{base}.gitbook.io")
    return suggestions


def _heuristic_value(url: str) -> float:
    parsed = urlparse(url)
    path = parsed.path.lower()
    score = 0.6
    for keyword in ("docs", "documentation", "guide", "handbook"):
        if keyword in path:
            score += 0.25
            break
    if any(token in path for token in ("blog", "kb", "support")):
        score += 0.1
    if "api" in path:
        score += 0.1
    if parsed.netloc.lower().endswith(('.org', '.io', '.dev')):
        score += 0.1
    return max(0.1, min(score, 1.5))


def _freshness_score(url: str, source: str) -> float:
    lowered = url.lower()
    if "sitemap" in lowered or source.startswith("sitemap"):
        return 1.0
    if any(token in lowered for token in ("rss", "atom", "feed")):
        return 0.9
    if "blog" in lowered or "news" in lowered:
        return 0.6
    return 0.2 if source == "seed" else 0.1


def _domain_from_url(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    return host[4:] if host.startswith("www.") else host


@lru_cache(maxsize=1)
def _load_value_map() -> Dict[str, float]:
    mapping: Dict[str, float] = {}
    # Curated seeds first.
    if CURATED_PATH.exists():
        with CURATED_PATH.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                url = payload.get("url")
                value = payload.get("value_prior", 0.0)
                if not isinstance(url, str):
                    continue
                domain = _domain_from_url(url)
                try:
                    numeric = float(value)
                except (TypeError, ValueError):
                    numeric = 0.0
                mapping[domain] = max(mapping.get(domain, 0.0), numeric)
    # Merge append-only seed store scores.
    for entry in seed_store.load_entries():
        domain = entry.get("domain")
        if not isinstance(domain, str):
            continue
        try:
            score = float(entry.get("score", 0.0))
        except (TypeError, ValueError):
            score = 0.0
        mapping[domain.strip().lower()] = max(mapping.get(domain.strip().lower(), 0.0), score)
    return mapping


def _candidate_with_scores(url: str, source: str, authority: AuthorityIndex) -> Candidate:
    sanitized = _sanitize_url(url)
    if not sanitized:
        raise ValueError("invalid url")
    domain = _domain_from_url(sanitized)
    value_prior = _load_value_map().get(domain, _heuristic_value(sanitized))
    freshness = _freshness_score(sanitized, source)
    host_authority = authority.score_for(domain)
    weight = 1.3 if source == "llm" else 1.0 if source == "seed" else 0.8
    return Candidate(
        url=sanitized,
        source=source,
        weight=weight,
        value_prior=value_prior,
        freshness_hint=freshness,
        host_authority=host_authority,
    )


def build_frontier(
    query: str,
    *,
    seed_domains: Optional[Sequence[str]] = None,
    extra_urls: Optional[Sequence[str]] = None,
    budget: Optional[int] = None,
    value_overrides: Optional[Mapping[str, float]] = None,
) -> List[Candidate]:
    """Return an ordered list of crawl candidates for the given query."""

    q = (query or "").strip()
    if not q:
        return []

    limit = DEFAULT_BUDGET if budget is None else max(1, int(budget))
    bloom = UrlBloom(capacity=limit * 5)
    value_map = dict(_load_value_map())
    for domain, score in (value_overrides or {}).items():
        value_map[domain] = max(value_map.get(domain, 0.0), float(score))
    authority = AuthorityIndex.load_default()

    candidates: List[Candidate] = []

    def _try_add(url: str, source: str) -> None:
        try:
            candidate = _candidate_with_scores(url, source, authority)
        except ValueError:
            return
        domain = _domain_from_url(candidate.url)
        if domain in value_map:
            candidate = Candidate(
                url=candidate.url,
                source=candidate.source,
                weight=candidate.weight,
                value_prior=max(candidate.value_prior, value_map[domain]),
                freshness_hint=candidate.freshness_hint,
                host_authority=candidate.host_authority,
            )
        if candidate.url in bloom:
            return
        bloom.add(candidate.url)
        candidates.append(candidate)

    for url in extra_urls or []:
        _try_add(url, "llm")
        if len(candidates) >= limit:
            break

    if len(candidates) < limit:
        for domain in seed_domains or []:
            base = (domain or "").strip()
            if not base:
                continue
            for url in _domain_candidates(base, q):
                _try_add(url, "seed")
                if len(candidates) >= limit:
                    break
            if len(candidates) >= limit:
                break

    if len(candidates) < limit:
        for url in _query_candidates(q):
            _try_add(url, "heuristic")
            if len(candidates) >= limit:
                break

    if not candidates:
        return []

    ordered = sorted(candidates, key=lambda item: item.priority, reverse=True)
    return ordered[:limit]
