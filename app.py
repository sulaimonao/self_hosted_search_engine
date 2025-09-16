"""Flask application exposing the search experience."""

from __future__ import annotations

import logging
import os
from typing import Optional

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

from search.indexer import create_or_open_index
from search.query import search as search_index

load_dotenv()

LOGGER = logging.getLogger(__name__)


def create_app() -> Flask:
    app = Flask(__name__, static_folder="static", template_folder="templates")

    index_dir = os.getenv("INDEX_DIR", "./data/index")
    crawl_store = os.getenv("CRAWL_STORE", "./data/crawl")
    default_limit = int(os.getenv("SEARCH_DEFAULT_LIMIT", "20"))

    app.config.update(
        INDEX_DIR=index_dir,
        CRAWL_STORE=crawl_store,
        SEARCH_DEFAULT_LIMIT=default_limit,
    )

    cache: dict[str, Optional[object]] = {"ix": None, "dir": None}

    def get_index():
        desired_dir = app.config["INDEX_DIR"]
        if cache["ix"] is None or cache["dir"] != desired_dir:
            try:
                cache["ix"] = create_or_open_index(desired_dir)
                cache["dir"] = desired_dir
            except Exception as exc:  # pragma: no cover - defensive
                LOGGER.exception("failed to initialize index at %s", desired_dir)
                cache["ix"] = None
        return cache["ix"]

    @app.get("/healthz")
    def healthz():
        return "ok", 200

    @app.get("/")
    def root():
        last_query = request.args.get("q", "")
        return render_template("index.html", query=last_query)

    @app.get("/search")
    def search():
        ix = get_index()
        query = request.args.get("q", "")
        limit = request.args.get("limit", type=int) or app.config["SEARCH_DEFAULT_LIMIT"]
        if ix is None:
            LOGGER.warning("search requested but index is unavailable")
            results: list[dict] = []
        else:
            results = search_index(ix, query, limit=limit)
        return jsonify({"query": query, "results": results})

    return app


if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    app = create_app()
    app.run(debug=True)
