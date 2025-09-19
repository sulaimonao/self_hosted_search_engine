"""Query helpers for the Whoosh index."""

from __future__ import annotations

import logging
from typing import List

from whoosh.highlight import ContextFragmenter, HtmlFormatter
from whoosh.qparser import MultifieldParser, PhrasePlugin, QueryParserError

LOGGER = logging.getLogger(__name__)


def search(
    ix,
    query: str,
    *,
    limit: int = 20,
    max_limit: int = 50,
    max_query_length: int = 256,
) -> List[dict]:
    """Execute the query against the provided index."""

    if ix is None:
        LOGGER.warning("search called without an index instance")
        return []

    q = (query or "").strip()
    if not q:
        return []

    if len(q) > max_query_length:
        q = q[:max_query_length]

    limit = max(1, min(int(limit or 1), max_limit))

    with ix.searcher() as searcher:
        parser = MultifieldParser(["title", "h1h2", "body", "url"], schema=ix.schema)
        parser.add_plugin(PhrasePlugin())
        try:
            parsed = parser.parse(q)
        except QueryParserError as exc:
            LOGGER.error("failed to parse query %s: %s", q, exc)
            return []
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.error("unexpected parse error for %s: %s", q, exc)
            return []

        hits = searcher.search(parsed, limit=limit)
        hits.fragmenter = ContextFragmenter(maxchars=240, surround=60)
        hits.formatter = HtmlFormatter(tagname="mark")

        results = []
        for hit in hits:
            snippet = hit.highlights("body") or (hit.get("body") or "")[:240]
            results.append(
                {
                    "title": hit.get("title") or hit.get("url") or "Untitled",
                    "url": hit.get("url"),
                    "snippet": snippet,
                    "score": float(hit.score),
                    "lang": hit.get("lang") or "unknown",
                }
            )
        return results
