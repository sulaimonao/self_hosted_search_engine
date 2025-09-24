#!/usr/bin/env python3
"""Command-line entry point for running Whoosh searches."""

from __future__ import annotations

import argparse
import os
from typing import Iterable

from search.indexer import create_or_open_index
from search.query import search as search_index


def format_rows(rows: Iterable[dict]) -> str:
    lines = [f"{'#':>3} | {'Score':>8} | Title", "-" * 72]
    for idx, row in enumerate(rows, start=1):
        score = f"{row.get('score', 0.0):.3f}"
        title = row.get("title") or "(untitled)"
        url = row.get("url") or ""
        lines.append(f"{idx:>3} | {score:>8} | {title}")
        if url:
            lines.append(f"      {url}")
        snippet = (row.get("snippet") or "").strip()
        if snippet:
            lines.append(f"      {snippet}")
        lines.append("-" * 72)
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Query the local Whoosh index")
    parser.add_argument("--q", required=True, help="Query string")
    parser.add_argument("--limit", type=int, default=10, help="Maximum number of results to return")
    args = parser.parse_args()

    index_dir = os.getenv("INDEX_DIR", "./data/whoosh")
    ix = create_or_open_index(index_dir)
    results = search_index(ix, args.q, limit=args.limit)
    if not results:
        print("No results found.")
        return
    print(format_rows(results))


if __name__ == "__main__":
    main()
