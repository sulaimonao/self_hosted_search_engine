"""Generate candidate URLs for focused crawling."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence
from urllib.parse import quote, urlparse, urlunparse

DEFAULT_BUDGET = int(os.getenv("FOCUSED_CRAWL_BUDGET", "50"))

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


def _add_candidate(collection: dict[str, Candidate], url: str, source: str, weight: float) -> None:
    sanitized = _sanitize_url(url)
    if not sanitized:
        return
    existing = collection.get(sanitized)
    if existing is None or weight > existing.weight:
        collection[sanitized] = Candidate(url=sanitized, source=source, weight=weight)


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


def build_frontier(
    query: str,
    *,
    seed_domains: Optional[Sequence[str]] = None,
    extra_urls: Optional[Sequence[str]] = None,
    budget: Optional[int] = None,
) -> List[Candidate]:
    """Return an ordered list of crawl candidates for the given query."""

    q = (query or "").strip()
    if not q:
        return []

    limit = DEFAULT_BUDGET if budget is None else max(1, int(budget))
    candidates: dict[str, Candidate] = {}

    for url in extra_urls or []:
        _add_candidate(candidates, url, source="llm", weight=1.3)
        if len(candidates) >= limit:
            break

    if len(candidates) < limit:
        for domain in seed_domains or []:
            base = (domain or "").strip()
            if not base:
                continue
            for url in _domain_candidates(base, q):
                _add_candidate(candidates, url, source="seed", weight=1.0)
                if len(candidates) >= limit:
                    break
            if len(candidates) >= limit:
                break

    if len(candidates) < limit:
        for url in _query_candidates(q):
            _add_candidate(candidates, url, source="heuristic", weight=0.8)
            if len(candidates) >= limit:
                break

    ordered_values = list(candidates.values())
    return ordered_values[:limit]
