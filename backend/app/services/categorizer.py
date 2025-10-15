"""Deterministic category helpers for documents."""

from __future__ import annotations

from typing import Tuple
from urllib.parse import urlparse


def deterministic_categories(
    url: str, text: str | None
) -> Tuple[list[str], str | None]:
    """Return (categories, site) derived from the URL and content heuristics."""

    categories: set[str] = set()
    parsed = urlparse(url or "")
    host = parsed.netloc.lower() if parsed.netloc else None
    if host:
        bare = host[4:] if host.startswith("www.") else host
        host = bare
        if "github.com" in bare:
            categories.add("code")
        if any(domain in bare for domain in ("arxiv.org", "doi.org")):
            categories.add("paper")
        if bare.endswith(".edu"):
            categories.add("education")
    if text:
        text_len = len(text)
        if text_len > 80_000:
            categories.add("longform")
        elif text_len > 20_000:
            categories.add("article")
    return sorted(categories), host


__all__ = ["deterministic_categories"]
