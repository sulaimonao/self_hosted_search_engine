"""Registry-backed discovery strategies for surfacing crawl seeds."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Iterator, Sequence
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree

import requests

LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from server.seeds_loader import SeedRegistryEntry

DISCOVERY_USER_AGENT = os.getenv(
    "DISCOVERY_USER_AGENT", "SelfHostedSearchBot/0.3 (+registry-discovery)"
)
FEED_TIMEOUT = float(os.getenv("DISCOVERY_FEED_TIMEOUT", "10"))

_WORD_RE = re.compile(r"[a-z0-9]+")


@dataclass(slots=True)
class StrategyCandidate:
    """Intermediate candidate returned by registry strategies."""

    url: str
    score: float = 0.0
    title: str | None = None
    summary: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


StrategyFn = Callable[["SeedRegistryEntry", str, int], Sequence[StrategyCandidate]]


def _keyword_tokens(query: str) -> list[str]:
    lowered = (query or "").lower()
    tokens = _WORD_RE.findall(lowered)
    return tokens


def _strip_tag(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1].lower()
    return tag.lower()


def _resolve_url(candidate: str, base_url: str) -> str | None:
    text = (candidate or "").strip()
    if not text:
        return None
    if text.startswith("//"):
        parsed = urlparse(base_url)
        scheme = parsed.scheme or "https"
        text = f"{scheme}:{text}"
    if text.startswith(("http://", "https://")):
        return text
    return urljoin(base_url, text)


def _extract_entry(
    element: ElementTree.Element, base_url: str
) -> tuple[str | None, str | None, str | None, dict[str, object]]:
    title: str | None = None
    summary_parts: list[str] = []
    link: str | None = None
    metadata: dict[str, object] = {}
    for child in list(element):
        name = _strip_tag(child.tag)
        if name == "title":
            text = " ".join(segment.strip() for segment in child.itertext() if segment.strip())
            if text:
                title = text
        elif name == "link":
            href = child.get("href") or " ".join(
                segment.strip() for segment in child.itertext() if segment.strip()
            )
            resolved = _resolve_url(href, base_url)
            if resolved:
                link = resolved
        elif name in {"description", "summary", "content"}:
            text = " ".join(segment.strip() for segment in child.itertext() if segment.strip())
            if text:
                summary_parts.append(text)
        elif name in {"id", "guid"}:
            identifier = " ".join(
                segment.strip() for segment in child.itertext() if segment.strip()
            )
            if identifier:
                metadata.setdefault("entry_id", identifier)
        elif name in {"updated", "published", "pubdate"}:
            timestamp = " ".join(
                segment.strip() for segment in child.itertext() if segment.strip()
            )
            if timestamp:
                metadata.setdefault("published", timestamp)
    if link is None:
        href = element.attrib.get("href") or element.attrib.get("url")
        resolved = _resolve_url(href, base_url) if href else None
        if resolved:
            link = resolved
    summary = " ".join(summary_parts).strip() or None
    return link, title, summary, metadata


def _iter_feed_entries(xml_text: str, base_url: str) -> Iterator[tuple[str, str | None, str | None, dict[str, object]]]:
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        LOGGER.debug("invalid feed payload for %s", base_url)
        return iter(())
    items: list[ElementTree.Element] = []
    for element in root.iter():
        tag = _strip_tag(element.tag)
        if tag in {"item", "entry"}:
            items.append(element)
    for element in items:
        link, title, summary, metadata = _extract_entry(element, base_url)
        if link:
            yield link, title, summary, metadata


def _score_entry(tokens: Sequence[str], title: str | None, summary: str | None) -> float:
    if not tokens:
        return 0.0
    corpus = " ".join(part for part in (title, summary) if part).lower()
    if not corpus:
        return 0.0
    hits = sum(1 for token in tokens if token in corpus)
    if not hits:
        return 0.0
    return hits / len(tokens)


def _root_url(url: str) -> str | None:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def rss_hub(entry: "SeedRegistryEntry", query: str, limit: int) -> list[StrategyCandidate]:
    """Fetch RSS/Atom feeds and rank entries by keyword overlap."""

    tokens = _keyword_tokens(query)
    cap = max(1, int(limit))
    candidates: list[StrategyCandidate] = []
    seen: set[str] = set()
    for feed_url in entry.entrypoints:
        added = False
        try:
            response = requests.get(
                feed_url,
                headers={
                    "User-Agent": DISCOVERY_USER_AGENT,
                    "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.8",
                },
                timeout=(5, FEED_TIMEOUT),
            )
            response.raise_for_status()
        except requests.RequestException as exc:  # pragma: no cover - network guard
            LOGGER.debug("rss_hub failed for %s: %s", feed_url, exc)
            response_text = ""
        else:
            response_text = response.text
        for link, title, summary, metadata in _iter_feed_entries(response_text, feed_url):
            if len(candidates) >= cap:
                break
            if link in seen:
                continue
            seen.add(link)
            score = _score_entry(tokens, title, summary)
            if score <= 0:
                score = 0.05
            metadata = dict(metadata)
            metadata.setdefault("feed", feed_url)
            candidates.append(
                StrategyCandidate(
                    url=link,
                    score=score,
                    title=title,
                    summary=summary,
                    metadata=metadata,
                )
            )
            added = True
        if not added:
            fallback = _root_url(feed_url)
            if fallback and fallback not in seen and len(candidates) < cap:
                seen.add(fallback)
                candidates.append(
                    StrategyCandidate(
                        url=fallback,
                        score=0.02,
                        metadata={"feed": feed_url, "fallback": True},
                    )
                )
        if len(candidates) >= cap:
            break
    return candidates[:cap]


def html_extract_links(entry: "SeedRegistryEntry", query: str, limit: int) -> list[StrategyCandidate]:
    """Placeholder for HTML link extraction strategy."""

    LOGGER.debug("html_extract_links strategy not yet implemented for %s", entry.id)
    return []


def github_topics(entry: "SeedRegistryEntry", query: str, limit: int) -> list[StrategyCandidate]:
    """Placeholder for GitHub topics strategy."""

    LOGGER.debug("github_topics strategy not yet implemented for %s", entry.id)
    return []


def curated_list(entry: "SeedRegistryEntry", query: str, limit: int) -> list[StrategyCandidate]:
    """Placeholder for curated list strategy."""

    LOGGER.debug("curated_list strategy not yet implemented for %s", entry.id)
    return []


def sitemap_index(entry: "SeedRegistryEntry", query: str, limit: int) -> list[StrategyCandidate]:
    """Placeholder for sitemap index discovery strategy."""

    LOGGER.debug("sitemap_index strategy not yet implemented for %s", entry.id)
    return []


STRATEGY_REGISTRY: dict[str, StrategyFn] = {
    "rss_hub": rss_hub,
    "feed": rss_hub,  # backwards-compatible alias
    "html_extract_links": html_extract_links,
    "github_topics": github_topics,
    "curated_list": curated_list,
    "sitemap_index": sitemap_index,
}


__all__ = ["StrategyCandidate", "STRATEGY_REGISTRY", "rss_hub"]


def external_search_strategy(query: str, limit: int = 10) -> list[StrategyCandidate]:
    """Use an external search provider to find new documents."""
    from .utils import google_search

    results = google_search(query, limit=limit)
    return [
        StrategyCandidate(url=r["link"], title=r["title"], summary=r["snippet"])
        for r in results
    ]
