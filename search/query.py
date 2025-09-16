"""Query helpers for the Whoosh index."""

from __future__ import annotations

import logging
from typing import List

from whoosh.highlight import ContextFragmenter, HtmlFormatter
from whoosh.qparser import MultifieldParser

LOGGER = logging.getLogger(__name__)


def search(ix, query: str, limit: int = 20) -> List[dict]:
    """Execute the query against the provided index."""

    if ix is None:
        LOGGER.warning("search called without an index instance")
        return []

    q = (query or "").strip()
    if not q:
        return []

    limit = max(1, int(limit or 1))

    with ix.searcher() as searcher:
        parser = MultifieldParser(["title", "text", "url"], schema=ix.schema)
        try:
            parsed = parser.parse(q)
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.error("failed to parse query %s: %s", q, exc)
            return []

        hits = searcher.search(parsed, limit=limit)
        hits.fragmenter = ContextFragmenter(maxchars=200, surround=40)
        hits.formatter = HtmlFormatter(tagname="mark")

        results = []
        for hit in hits:
            snippet = hit.highlights("text") or (hit.get("text") or "")[:200]
            results.append(
                {
                    "title": hit.get("title") or hit.get("url") or "Untitled",
                    "url": hit.get("url"),
                    "snippet": snippet,
                    "score": float(hit.score),
                }
            )
        return results
