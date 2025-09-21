"""Seed URL provider used by the cold-start indexer."""

from __future__ import annotations

from urllib.parse import quote

import requests


WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"


def _wiki_search(query: str, limit: int) -> list[str]:
    try:
        response = requests.get(
            WIKIPEDIA_API,
            params={
                "action": "opensearch",
                "format": "json",
                "limit": limit,
                "search": query,
            },
            timeout=5,
        )
        response.raise_for_status()
    except requests.RequestException:
        return []
    try:
        payload = response.json()
    except ValueError:
        return []
    urls = payload[3] if isinstance(payload, list) and len(payload) >= 4 else []
    return [url for url in urls if isinstance(url, str)]


def seed_urls_for_query(query: str, limit: int = 5) -> list[str]:
    """Return candidate URLs to crawl for the supplied query."""

    query = query.strip()
    if not query:
        return []
    urls = _wiki_search(query, limit)
    if urls:
        return urls[:limit]
    fallback = f"https://en.wikipedia.org/wiki/{quote(query.replace(' ', '_'))}"
    return [fallback]


__all__ = ["seed_urls_for_query"]
