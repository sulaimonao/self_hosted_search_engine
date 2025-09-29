"""Flask application factory."""

from __future__ import annotations

import logging
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Optional

import yaml

import requests
from flask import Flask, current_app, jsonify, render_template, request
from flask_cors import CORS
from urllib.parse import urlparse


LOGGER = logging.getLogger(__name__)
EMBEDDING_MODEL_PATTERNS = [
    re.compile(r"(?:^|[-_:])embed(?:ding)?", re.IGNORECASE),
    re.compile(r"(?:^|[-_:])gte[-_:]", re.IGNORECASE),
    re.compile(r"(?:^|[-_:])bge[-_:]", re.IGNORECASE),
    re.compile(r"(?:^|[-_:])text2vec", re.IGNORECASE),
    re.compile(r"(?:^|[-_:])e5[-_:]", re.IGNORECASE),
]

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.yaml"


def _is_embedding_model(name: str) -> bool:
    return any(pattern.search(name) for pattern in EMBEDDING_MODEL_PATTERNS)


def create_app() -> Flask:
    from backend.agent.document_store import DocumentStore
    from backend.agent.frontier_store import FrontierStore
    from backend.agent.runtime import AgentRuntime, CrawlFetcher
    from backend.retrieval.vector_store import LocalVectorStore
    from engine.indexing.crawl import CrawlClient

    from .api import agent_tools as agent_tools_api
    from .api import chat as chat_api
    from .api import diagnostics as diagnostics_api
    from .api import jobs as jobs_api
    from .api import metrics as metrics_api
    from .api import refresh as refresh_api
    from .api import research as research_api
    from .api import seeds as seeds_api
    from .api import search as search_api
    from .config import AppConfig
    from .jobs.focused_crawl import FocusedCrawlManager
    from .jobs.runner import JobRunner
    from .metrics import metrics as metrics_module
    from .search.service import SearchService
    from server.refresh_worker import RefreshWorker
    from server.learned_web_db import get_db
    from server import middleware_logging

    metrics = metrics_module

    package_root = Path(__file__).resolve().parents[2]
    static_folder = package_root / "static"
    template_folder = package_root / "templates"
    app = Flask(
        __name__,
        static_folder=str(static_folder),
        template_folder=str(template_folder),
    )

    app.before_request(middleware_logging.before_request)
    app.after_request(middleware_logging.after_request)

    frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://127.0.0.1:3100").strip()

    def _collect_allowed_origins(origin: str) -> list[str]:
        allowed: list[str] = []

        def _add(candidate: str | None) -> None:
            if not candidate:
                return
            cleaned = candidate.rstrip("/")
            if cleaned and cleaned not in allowed:
                allowed.append(cleaned)

        _add(origin)

        parsed = urlparse(origin)
        scheme = parsed.scheme or "http"
        default_port = os.getenv("FRONTEND_PORT") or parsed.port or 3100
        try:
            port = int(default_port)
        except (TypeError, ValueError):
            port = 3100
        port_text = str(port)
        hostname = parsed.hostname or "127.0.0.1"
        host_aliases = {hostname}
        if hostname in {"127.0.0.1", "0.0.0.0"}:
            host_aliases.add("localhost")
        elif hostname == "localhost":
            host_aliases.add("127.0.0.1")
        else:
            host_aliases.add("127.0.0.1")
            host_aliases.add("localhost")
        for host in host_aliases:
            _add(f"{scheme}://{host}:{port_text}")
        if port in {80, 443}:
            for host in host_aliases:
                _add(f"{scheme}://{host}")
        return allowed

    allowed_origins = _collect_allowed_origins(frontend_origin)
    app.config.setdefault("FRONTEND_ORIGIN", frontend_origin)
    app.config.setdefault("FRONTEND_ALLOWED_ORIGINS", tuple(allowed_origins))
    CORS(
        app,
        resources={r"/api/*": {"origins": allowed_origins}},
        supports_credentials=True,
        expose_headers=["X-Request-Id"],
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

    documents_dir = config.agent_data_dir / "documents"
    vector_dir = config.agent_data_dir / "vector_store"
    frontier_store = FrontierStore(config.frontier_db_path)
    document_store = DocumentStore(documents_dir)
    vector_store = LocalVectorStore(vector_dir)
    crawler_client = CrawlClient(
        user_agent=os.getenv("AGENT_USER_AGENT", "SelfHostedSearchAgent/0.1"),
        request_timeout=float(os.getenv("AGENT_REQUEST_TIMEOUT", "15")),
        read_timeout=float(os.getenv("AGENT_READ_TIMEOUT", "30")),
        min_delay=float(os.getenv("AGENT_MIN_DELAY", "1.0")),
    )
    fetcher = CrawlFetcher(crawler_client)

    with CONFIG_PATH.open("r", encoding="utf-8") as handle:
        raw_yaml = yaml.safe_load(handle) or {}
    agent_settings = raw_yaml.get("agent", {}) if isinstance(raw_yaml, dict) else {}
    agent_max_fetch = int(agent_settings.get("max_fetch_per_turn", config.agent_max_fetch_per_turn))
    agent_coverage_threshold = float(
        agent_settings.get("coverage_threshold", config.agent_coverage_threshold)
    )
    agent_runtime = AgentRuntime(
        search_service=search_service,
        frontier=frontier_store,
        document_store=document_store,
        vector_store=vector_store,
        fetcher=fetcher,
        max_fetch_per_turn=agent_max_fetch,
        coverage_threshold=agent_coverage_threshold,
    )

    app.config.update(
        APP_CONFIG=config,
        JOB_RUNNER=runner,
        FOCUSED_MANAGER=manager,
        SEARCH_SERVICE=search_service,
        REFRESH_WORKER=refresh_worker,
        LEARNED_WEB_DB=db,
        AGENT_RUNTIME=agent_runtime,
    )
    app.config.setdefault(
        "SEED_REGISTRY_PATH",
        Path(__file__).resolve().parents[2] / "seeds" / "registry.yaml",
    )
    app.config.setdefault("SEED_WORKSPACE_DIRECTORY", "workspace")

    app.register_blueprint(search_api.bp)
    app.register_blueprint(jobs_api.bp)
    app.register_blueprint(chat_api.bp)
    app.register_blueprint(research_api.bp)
    app.register_blueprint(diagnostics_api.bp)
    app.register_blueprint(metrics_api.bp)
    app.register_blueprint(refresh_api.bp)
    app.register_blueprint(agent_tools_api.bp)
    app.register_blueprint(seeds_api.bp)

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
        installed: set[str] = set()
        if tags:
            for entry in tags.get("models", []):
                if isinstance(entry, str):
                    name = entry.strip()
                elif isinstance(entry, dict):
                    raw = entry.get("name")
                    name = raw.strip() if isinstance(raw, str) else ""
                else:
                    name = ""
                if not name:
                    continue
                installed.add(name)
                if ":" in name:
                    installed.add(name.split(":", 1)[0])

        engine_config: EngineConfig | None = current_app.config.get("RAG_ENGINE_CONFIG")
        configured: list[tuple[str, str]] = []
        if engine_config is not None:
            primary = (engine_config.models.llm_primary or "").strip()
            fallback = (engine_config.models.llm_fallback or "").strip()
            embed = (engine_config.models.embed or "").strip()
            for name, role in (
                (primary, "primary"),
                (fallback, "fallback"),
                (embed, "embedding"),
            ):
                if name and all(existing[0] != name for existing in configured):
                    configured.append((name, role))

        models: list[dict[str, object]] = []
        ollama_running = bool(tags)
        for name, role in configured:
            kind = "embedding" if role == "embedding" else "chat"
            model_payload = {
                "name": name,
                "role": role,
                "kind": kind,
                "installed": name in installed,
                "available": name in installed and ollama_running,
            }
            models.append(model_payload)

        extras = []
        if installed:
            configured_names = {entry[0] for entry in configured}
            for name in installed:
                if name in configured_names:
                    continue
                extras.append(
                    {
                        "name": name,
                        "role": "extra",
                        "kind": "embedding" if _is_embedding_model(name) else "chat",
                        "installed": True,
                        "available": ollama_running,
                    }
                )
        if extras:
            models.extend(sorted(extras, key=lambda item: str(item["name"]).lower()))

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
