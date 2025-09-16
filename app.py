"""Flask application exposing the search experience."""

from __future__ import annotations

import logging
import os
import subprocess
from typing import Optional

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

from llm.seed_guesser import guess_urls as llm_guess_urls
from search.indexer import create_or_open_index
from search.smart_search import smart_search

load_dotenv()

LOGGER = logging.getLogger(__name__)


def create_app() -> Flask:
    app = Flask(__name__, static_folder="static", template_folder="templates")

    index_dir = os.getenv("INDEX_DIR", "./data/index")
    crawl_store = os.getenv("CRAWL_STORE", "./data/crawl")
    default_limit = int(os.getenv("SEARCH_DEFAULT_LIMIT", "20"))
    smart_min_results = int(os.getenv("SMART_MIN_RESULTS", "5"))
    ollama_host = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")

    app.config.update(
        INDEX_DIR=index_dir,
        CRAWL_STORE=crawl_store,
        SEARCH_DEFAULT_LIMIT=default_limit,
        SMART_MIN_RESULTS=smart_min_results,
        OLLAMA_HOST=ollama_host,
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

    def _ollama_host() -> str:
        return str(app.config.get("OLLAMA_HOST", "http://127.0.0.1:11434")).rstrip("/")

    def _ollama_installed() -> bool:
        try:
            result = subprocess.run(
                ["ollama", "--version"],
                check=False,
                capture_output=True,
            )
        except FileNotFoundError:
            return False
        return result.returncode == 0

    def _ollama_tags() -> Optional[dict]:
        host = _ollama_host()
        try:
            response = requests.get(f"{host}/api/tags", timeout=3)
            response.raise_for_status()
        except requests.RequestException:
            return None
        try:
            return response.json()
        except ValueError:  # pragma: no cover - defensive
            return None

    @app.get("/healthz")
    def healthz():
        return "ok", 200

    @app.get("/")
    def root():
        last_query = request.args.get("q", "")
        return render_template(
            "index.html",
            query=last_query,
            smart_min_results=app.config["SMART_MIN_RESULTS"],
        )

    @app.get("/search")
    def search():
        ix = get_index()
        query = request.args.get("q", "")
        limit = request.args.get("limit", type=int) or app.config["SEARCH_DEFAULT_LIMIT"]
        llm_param = (request.args.get("llm") or "").lower()
        use_llm: Optional[bool]
        if llm_param == "on":
            use_llm = True
        elif llm_param == "off":
            use_llm = False
        else:
            use_llm = None
        model = (request.args.get("model") or "").strip() or None

        results = smart_search(ix, query, limit=limit, use_llm=use_llm, model=model)
        return jsonify({"query": query, "results": results})

    @app.get("/api/llm/status")
    def llm_status():
        installed = _ollama_installed()
        tags = _ollama_tags()
        running = tags is not None
        return jsonify({"installed": installed, "running": running, "host": _ollama_host()})

    @app.get("/api/llm/models")
    def llm_models():
        tags = _ollama_tags()
        models: list[dict] = []
        if tags:
            for model in tags.get("models", []):
                name = model.get("name") if isinstance(model, dict) else None
                if isinstance(name, str) and name:
                    models.append({"name": name})
        return jsonify({"models": models})

    @app.post("/api/llm/guess-seeds")
    def llm_guess():
        payload = request.get_json(silent=True) or {}
        query = (payload.get("q") or "").strip()
        model = (payload.get("model") or "").strip() or None
        if not query:
            return jsonify({"error": "Missing 'q' parameter"}), 400
        urls = llm_guess_urls(query, model=model)
        return jsonify({"urls": urls})

    return app


if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    app = create_app()
    app.run(debug=True)
