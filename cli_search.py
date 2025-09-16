#!/usr/bin/env python3
from __future__ import annotations

import argparse

from whoosh import index
from whoosh.highlight import HtmlFormatter
from whoosh.qparser import MultifieldParser, OrGroup, QueryParser
from whoosh.query import And, Term

from config import index_dir, load_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Command-line search over the local index")
    parser.add_argument("query", nargs="+", help="Search terms")
    parser.add_argument("--site", help="Restrict results to a domain")
    parser.add_argument("--in-title", action="store_true", help="Search titles only")
    parser.add_argument("--limit", type=int, default=10, help="Number of results to show")
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    cfg = load_config()
    idx_path = index_dir(cfg)
    if not index.exists_in(idx_path):
        raise SystemExit(f"Index not found at {idx_path}. Run index_build.py first.")
    ix = index.open_dir(idx_path)

    query_text = " ".join(args.query)
    parser_cls = QueryParser("title", ix.schema, group=OrGroup) if args.in_title else MultifieldParser(["title", "content"], ix.schema, group=OrGroup)
    query = parser_cls.parse(query_text)
    if args.site:
        query = And([query, Term("domain", args.site.lower())])

    with ix.searcher() as searcher:
        results = searcher.search(query, limit=args.limit)
        results.fragmenter.charlimit = None
        results.fragmenter.maxchars = 200
        results.formatter = HtmlFormatter(tagname="mark")
        for hit in results:
            snippet = hit.highlights("content") or hit.highlights("title") or ""
            print(f"{hit.get('title', '(untitled)')} -> {hit.get('url')}\n  {snippet}\n")


if __name__ == "__main__":
    main()
