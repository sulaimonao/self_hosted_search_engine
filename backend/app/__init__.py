"""Flask application factory."""

from __future__ import annotations

import logging
import re
import subprocess
import time
from pathlib import Path
from typing import Optional

import requests
from flask import Flask, jsonify, render_template, request


LOGGER = logging.getLogger(__name__)
EMBEDDING_MODEL_PATTERNS = [
    re.compile(r"(?:^|[-_:])embed(?:ding)?", re.IGNORECASE),
    re.compile(r"(?:^|[-_:])gte[-_:]", re.IGNORECASE),
    re.compile(r"(?:^|[-_:])bge[-_:]", re.IGNORECASE),
    re.compile(r"(?:^|[-_:])text2vec", re.IGNORECASE),
    re.compile(r"(?:^|[-_:])e5[-_:]", re.IGNORECASE),
]


def _is_embedding_model(name: str) -> bool:
    return any(pattern.search(name) for pattern in EMBEDDING_MODEL_PATTERNS)


def create_app() -> Flask:
    from .api import chat as chat_api
    from .api import jobs as jobs_api
    from .api import metrics as metrics_api
    from .api import refresh as refresh_api
    from .api import research as research_api
    from .api import search as search_api
    from .config import AppConfig
    from .jobs.focused_crawl import FocusedCrawlManager
    from .jobs.runner import JobRunner
    from .metrics import metrics as metrics_module
    from .search.service import SearchService
    from server.refresh_worker import RefreshWorker
    from server.learned_web_db import get_db

    metrics = metrics_module

    package_root = Path(__file__).resolve().parents[2]
    static_folder = package_root / "static"
    template_folder = package_root / "templates"
    app = Flask(
        __name__,
        static_folder=str(static_folder),
        template_folder=str(template_folder),
    )

    config = AppConfig.from_env()
    config.ensure_dirs()
    config.log_summary()

    chat_logger = logging.getLogger("backend.app.api.chat")
    chat_logger.setLevel(config.chat_log_level)
    chat_logger.propagate = True
    app.config.setdefault("CHAT_LOGGER", chat_logger)

    db = get_db(config.learned_web_db_path)
    runner = JobRunner(config.logs_dir)
    manager = FocusedCrawlManager(config, runner, db)
    search_service = SearchService(config, manager)
    refresh_worker = RefreshWorker(config, search_service=search_service, db=db)

    app.config.update(
        APP_CONFIG=config,
        JOB_RUNNER=runner,
        FOCUSED_MANAGER=manager,
        SEARCH_SERVICE=search_service,
        REFRESH_WORKER=refresh_worker,
        LEARNED_WEB_DB=db,
    )

    app.register_blueprint(search_api.bp)
    app.register_blueprint(jobs_api.bp)
    app.register_blueprint(chat_api.bp)
    app.register_blueprint(research_api.bp)
    app.register_blueprint(metrics_api.bp)
    app.register_blueprint(refresh_api.bp)

    @app.get("/healthz")
    def healthz():
        return "ok", 200

    @app.get("/")
    def root():
        last_query = request.args.get("q", "")
        return render_template(
            "index.html",
            query=last_query,
            smart_min_results=config.smart_min_results,
        )

    @app.get("/search")
    def legacy_search():
        return search_api.search_endpoint()

    def _ollama_host() -> str:
        return config.ollama_url

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
        try:
            response = requests.get(f"{_ollama_host()}/api/tags", timeout=3)
            response.raise_for_status()
        except requests.RequestException:
            return None
        try:
            return response.json()
        except ValueError:  # pragma: no cover - defensive
            return None

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
                name: Optional[str]
                if isinstance(model, str):
                    name = model
                elif isinstance(model, dict):
                    candidate = model.get("name")
                    name = candidate if isinstance(candidate, str) else None
                else:
                    name = None
                if not name:
                    continue
                cleaned = name.strip()
                if cleaned and not _is_embedding_model(cleaned):
                    models.append({"name": cleaned})
        return jsonify({"models": models})

    @app.post("/api/llm/guess-seeds")
    def llm_guess():
        from llm.seed_guesser import guess_urls as llm_guess_urls

        payload = request.get_json(silent=True) or {}
        query = (payload.get("q") or "").strip()
        model = (payload.get("model") or "").strip() or None
        if not query:
            return jsonify({"error": "Missing 'q' parameter"}), 400
        start = time.perf_counter()
        urls = llm_guess_urls(query, model=model)
        metrics.record_llm_seed_time((time.perf_counter() - start) * 1000)
        return jsonify({"urls": urls})

    return app
