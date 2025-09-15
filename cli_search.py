#!/usr/bin/env python3
"""
Command‑line search utility for the self‑hosted search engine.

Usage:
    python cli_search.py <search terms>

It opens the Whoosh index and performs a search across the title and
content fields, returning the top results.  Useful for quick tests
without running the Flask web app.
"""
import sys
from whoosh import index
from whoosh.qparser import MultifieldParser, OrGroup

def main(args):
    if not args:
        print("Usage: python cli_search.py <search terms>")
        return

    query_str = " ".join(args)
    ix_dir = "index"

    try:
        ix = index.open_dir(ix_dir)
    except Exception as exc:
        print(f"Error opening index at {ix_dir}: {exc}")
        return

    with ix.searcher() as s:
        parser = MultifieldParser(["title", "content"], ix.schema, group=OrGroup)
        query = parser.parse(query_str)
        results = s.search(query, limit=10)
        for hit in results:
            title = hit.get("title") or "(untitled)"
            url = hit.get("url")
            print(f"{title} -> {url}")

if __name__ == "__main__":
    main(sys.argv[1:])