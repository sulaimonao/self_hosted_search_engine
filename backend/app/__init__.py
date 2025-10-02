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
from flask import Flask, Response, current_app, jsonify, request
from flask_cors import CORS

from observability import configure_tracing


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
    from backend.app.services.vector_index import VectorIndexService
    from engine.indexing.crawl import CrawlClient

    from engine.config import EngineConfig

    from .api import agent_tools as agent_tools_api
    from .api import agent_browser as agent_browser_api
    from .api import chat as chat_api
    from .api import discovery as discovery_api
    from .api import extract as extract_api
    from .api import llm as llm_api
    from .api import diagnostics as diagnostics_api
    from .api import index as index_api
    from .api import jobs as jobs_api
    from .api import metrics as metrics_api
    from .api import refresh as refresh_api
    from .api import shadow as shadow_api
    from .api import research as research_api
    from .api import seeds as seeds_api
    from .api import search as search_api
    from .config import AppConfig
    from .jobs.focused_crawl import FocusedCrawlManager
    from .jobs.runner import JobRunner
    from .shadow import ShadowIndexer
    from .metrics import metrics as metrics_module
    from .search.service import SearchService
    from server.refresh_worker import RefreshWorker
    from server.learned_web_db import get_db
    from .middleware import request_id as request_id_middleware
    from server import middleware_logging

    metrics = metrics_module

    app = Flask(__name__)

    langsmith_project = (
        os.getenv("LANGSMITH_PROJECT")
        or os.getenv("LANGCHAIN_PROJECT")
        or "self-hosted-search"
    )
    langsmith_enabled = os.getenv("LANGSMITH_ENABLED", "0").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    app.config.setdefault("LANGSMITH_PROJECT", langsmith_project)
    app.config.setdefault("LANGSMITH_ENABLED", langsmith_enabled)

    configure_tracing(
        app,
        enabled=langsmith_enabled,
        project_name=langsmith_project,
        service_name="self_hosted_search_engine.api",
    )

    app.before_request(request_id_middleware.before_request)
    app.after_request(request_id_middleware.after_request)
    app.before_request(middleware_logging.before_request)
    app.after_request(middleware_logging.after_request)

    CORS(app, resources={r"/api/*": {"origins": ["http://127.0.0.1:3100", "http://localhost:3100"]}})

    @app.before_request
    def _api_only_gate():
        path = request.path or ""
        if path == "/" or path.startswith("/api/") or request.endpoint:
            return None
        return (
            jsonify({"error": "Not Found", "hint": "UI served from frontend at :3100"}),
            404,
        )

    @app.post("/api/dev/log")
    def dev_log() -> Response:
        """Forward frontend dev instrumentation to stdout when developing."""

        if os.getenv("NODE_ENV") == "production":
            return jsonify({"ok": False, "reason": "disabled"}), 403

        payload = request.get_json(silent=True)
        if payload is None:
            payload = {"_raw": request.data.decode("utf-8", "ignore")}

        print({"lvl": "DEBUG", "evt": "ui.devlog", "data": payload}, flush=True)
        return jsonify({"ok": True}), 200

    config = AppConfig.from_env()
    config.ensure_dirs()
    config.log_summary()

    engine_config = EngineConfig.from_yaml(CONFIG_PATH)
    app.config.setdefault("RAG_ENGINE_CONFIG", engine_config)

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
    frontier_store = FrontierStore(config.frontier_db_path)
    document_store = DocumentStore(documents_dir)
    vector_index_service = VectorIndexService(
        engine_config=engine_config,
        app_config=config,
    )
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
        vector_index=vector_index_service,
        fetcher=fetcher,
        max_fetch_per_turn=agent_max_fetch,
        coverage_threshold=agent_coverage_threshold,
    )

    feature_agent_mode = os.getenv("FEATURE_AGENT_MODE", "0").lower() in {"1", "true", "yes", "on"}
    app.config.setdefault("FEATURE_AGENT_MODE", feature_agent_mode)

    feature_local_discovery = (
        os.getenv("FEATURE_LOCAL_DISCOVERY", "0").lower() in {"1", "true", "yes", "on"}
    )
    app.config.setdefault("FEATURE_LOCAL_DISCOVERY", feature_local_discovery)

    reload_enabled = os.getenv("BACKEND_RELOAD", "0").lower() in {"1", "true", "yes", "on"}

    if feature_local_discovery:
        from .services.local_discovery import LocalDiscoveryService

        home_downloads = Path.home() / "Downloads"
        data_downloads = config.agent_data_dir.parent / "downloads"
        candidate_dirs = []
        if home_downloads.exists() and home_downloads.is_dir():
            candidate_dirs.append(home_downloads)
        candidate_dirs.append(data_downloads)

        unique_dirs: list[Path] = []
        seen: set[Path] = set()
        for directory in candidate_dirs:
            try:
                resolved = directory.resolve()
            except OSError:
                continue
            if resolved in seen:
                continue
            seen.add(resolved)
            unique_dirs.append(directory)

        service: LocalDiscoveryService | None = None
        should_start = not reload_enabled or os.getenv("WERKZEUG_RUN_MAIN") == "true"
        if should_start and unique_dirs:
            ledger_path = config.agent_data_dir / "local_discovery_confirmations.json"
            service = LocalDiscoveryService(unique_dirs, ledger_path=ledger_path)
            try:
                service.start()
            except Exception:  # pragma: no cover - defensive logging
                LOGGER.exception("Local discovery service failed to start")
                service = None
            else:
                import atexit

                atexit.register(service.stop)

        app.config.setdefault("LOCAL_DISCOVERY_SERVICE", service)
    else:
        app.config.setdefault("LOCAL_DISCOVERY_SERVICE", None)

    browser_manager = None
    if feature_agent_mode:
        try:
            from .services.agent_browser import AgentBrowserManager

            browser_manager = AgentBrowserManager()
        except Exception:  # pragma: no cover - defensive logging
            LOGGER.exception("Agent browser manager unavailable; disabling agent browser endpoints")
            app.config.setdefault("AGENT_BROWSER_MANAGER", None)
        else:
            app.config.setdefault("AGENT_BROWSER_MANAGER", browser_manager)
    else:
        app.config.setdefault("AGENT_BROWSER_MANAGER", None)

    app.config.update(
        APP_CONFIG=config,
        JOB_RUNNER=runner,
        FOCUSED_MANAGER=manager,
        SEARCH_SERVICE=search_service,
        REFRESH_WORKER=refresh_worker,
        LEARNED_WEB_DB=db,
        AGENT_RUNTIME=agent_runtime,
        VECTOR_INDEX_SERVICE=vector_index_service,
    )
    shadow_manager = ShadowIndexer(app=app, runner=runner, vector_index=vector_index_service)
    app.config.setdefault("SHADOW_INDEX_MANAGER", shadow_manager)
    app.config.setdefault(
        "SEED_REGISTRY_PATH",
        Path(__file__).resolve().parents[2] / "seeds" / "registry.yaml",
    )
    app.config.setdefault("SEED_WORKSPACE_DIRECTORY", "workspace")

    app.register_blueprint(search_api.bp)
    app.register_blueprint(jobs_api.bp)
    app.register_blueprint(chat_api.bp)
    app.register_blueprint(llm_api.bp)
    app.register_blueprint(research_api.bp)
    app.register_blueprint(diagnostics_api.bp)
    app.register_blueprint(metrics_api.bp)
    app.register_blueprint(refresh_api.bp)
    app.register_blueprint(agent_tools_api.bp)
    app.register_blueprint(seeds_api.bp)
    app.register_blueprint(extract_api.bp)
    app.register_blueprint(index_api.bp)
    app.register_blueprint(discovery_api.bp)
    app.register_blueprint(shadow_api.bp)
    if feature_agent_mode and browser_manager is not None:
        app.register_blueprint(agent_browser_api.bp)

    @app.get("/api/healthz")
    def healthz() -> tuple[dict[str, str], int]:
        return {"status": "ok"}, 200

    @app.get("/")
    def root() -> Response:
        repo_root = Path(__file__).resolve().parents[2]
        candidate_paths = [
            repo_root / "frontend" / "dist" / "index.html",
            repo_root / "frontend" / "build" / "index.html",
        ]
        for path in candidate_paths:
            if path.exists():
                try:
                    html = path.read_text("utf-8")
                except OSError:
                    break
                return current_app.response_class(html, mimetype="text/html")
        fallback = """<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><title>Self-Hosted Search</title></head>
<body><main><h1>Self-Hosted Search API</h1><section id=\"diagnostics-panel\"><p>The frontend build is unavailable.</p>
<button id=\"diagnostics-run\">Run diagnostics</button><a id=\"diagnostics-download\" href=\"/api/diagnostics/report\">Download report</a>
<a id=\"diagnostics-log-download\" href=\"/api/diagnostics/logs\">Download logs</a></section></main></body></html>"""
        return current_app.response_class(fallback, mimetype="text/html")

    @app.errorhandler(404)
    def _not_found(_):
        return jsonify({"error": "Not Found"}), 404

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

    def _configured_models() -> dict[str, str | None]:
        engine_config = current_app.config.get("RAG_ENGINE_CONFIG")
        primary = "gpt-oss"
        fallback: str | None = "gemma3"
        embed = "embeddinggemma"
        if engine_config is not None:
            primary = (engine_config.models.llm_primary or primary).strip() or primary
            fallback_value = (engine_config.models.llm_fallback or "").strip()
            fallback = fallback_value or None
            embed = (engine_config.models.embed or embed).strip() or embed
        return {"primary": primary, "fallback": fallback, "embedder": embed}

    @app.get("/api/llm/status")
    def llm_status():
        installed = _ollama_installed()
        tags = _ollama_tags()
        running = tags is not None
        return jsonify({"installed": installed, "running": running, "host": _ollama_host()})

    @app.get("/api/llm/models")
    def llm_models():
        tags = _ollama_tags()
        available: list[str] = []
        if tags:
            seen: set[str] = set()
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
                if name not in seen:
                    available.append(name)
                    seen.add(name)
        available.sort(key=lambda value: value.lower())

        configured = _configured_models()
        return jsonify(
            {
                "available": available,
                "configured": configured,
                "ollama_host": _ollama_host(),
            }
        )

    @app.get("/api/llm/health")
    def llm_health():
        start = time.perf_counter()
        tags = _ollama_tags()
        duration_ms = int((time.perf_counter() - start) * 1000)
        reachable = tags is not None
        count = 0
        if tags and isinstance(tags.get("models"), list):
            count = len(tags["models"])  # type: ignore[index]
        return jsonify(
            {
                "reachable": reachable,
                "model_count": count,
                "duration_ms": duration_ms,
                "host": _ollama_host(),
            }
        )

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
