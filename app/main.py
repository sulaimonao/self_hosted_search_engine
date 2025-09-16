#!/usr/bin/env python3
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict

from flask import Flask, render_template, request
from whoosh import index
from whoosh.highlight import HtmlFormatter
from whoosh.qparser import MultifieldParser, OrGroup, QueryParser
from whoosh.query import And, Term

from config import index_dir, load_config


def _open_index(cfg: Dict[str, Any]):
    path = index_dir(cfg)
    if not index.exists_in(path):
        raise RuntimeError(f"Whoosh index not found at {path}. Run index_build.py first.")
    return index.open_dir(path)


def create_app(cfg: Dict[str, Any] | None = None) -> Flask:
    config = cfg or load_config()
    app = Flask(__name__)
    app.config.update(config)
    ix = _open_index(config)
    ui_cfg = config["ui"]
    field_boosts = config["index"].get("field_boosts", {})

    def _build_parser(in_title: bool = False):
        if in_title:
            return QueryParser("title", ix.schema, group=OrGroup)
        return MultifieldParser(["title", "content"], ix.schema, fieldboosts=field_boosts, group=OrGroup)

    @app.route("/")
    def home():
        return render_template("home.html", q="", site_filter="", in_title=False, ui=ui_cfg)

    @app.route("/search")
    def search():
        q = request.args.get("q", "").strip()
        page = max(int(request.args.get("page", 1)), 1)
        site_filter = request.args.get("site", "").strip()
        in_title = request.args.get("in_title") == "on"
        per_page = int(ui_cfg.get("page_len", 10))
        results = []
        total = 0
        latency_ms = 0.0
        if q:
            start = time.perf_counter()
            parser = _build_parser(in_title)
            try:
                query = parser.parse(q)
            except Exception:
                query = parser.parse("")
            if site_filter:
                term = Term("domain", site_filter.lower())
                query = And([query, term])
            with ix.searcher() as searcher:
                hits = searcher.search_page(query, page, pagelen=per_page, terms=True)
                hits.fragmenter.charlimit = None
                hits.fragmenter.maxchars = 280
                hits.formatter = HtmlFormatter(tagname="mark")
                for hit in hits:
                    results.append(
                        {
                            "title": hit.get("title", "(untitled)"),
                            "url": hit.get("url"),
                            "snippet": hit.highlights("content") or hit.highlights("title") or "",
                            "domain": hit.get("domain", ""),
                        }
                    )
                total = hits.total
            latency_ms = (time.perf_counter() - start) * 1000
        return render_template(
            "results.html",
            q=q,
            results=results,
            total=total,
            page=page,
            per_page=per_page,
            site_filter=site_filter,
            in_title=in_title,
            latency_ms=latency_ms,
            ui=ui_cfg,
        )

    @app.route("/healthz")
    def healthz():
        return {"status": "ok"}

    return app


def main() -> None:
    cfg = load_config()
    app = create_app(cfg)
    app.run(host=cfg["ui"]["host"], port=int(cfg["ui"]["port"]), debug=False)


if __name__ == "__main__":
    main()
