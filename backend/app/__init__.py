"""Flask application factory."""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import threading
from collections import deque
from pathlib import Path
from datetime import datetime
from typing import Optional

import yaml

import requests
from flask import Flask, Response, current_app, jsonify, request, render_template
from flask_cors import CORS

from observability import configure_tracing
from .logging_setup import setup_logging
from backend.app.observability import install_requests_logging


LOGGER = logging.getLogger(__name__)
EMBEDDING_MODEL_PATTERNS = [
    re.compile(r"(?:^|[-_:])embed(?:ding)?", re.IGNORECASE),
    re.compile(r"(?:^|[-_:])gte[-_:]", re.IGNORECASE),
    re.compile(r"(?:^|[-_:])bge[-_:]", re.IGNORECASE),
    re.compile(r"(?:^|[-_:])text2vec", re.IGNORECASE),
    re.compile(r"(?:^|[-_:])e5[-_:]", re.IGNORECASE),
]

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.yaml"

install_requests_logging()


def _is_embedding_model(name: str) -> bool:
    return any(pattern.search(name) for pattern in EMBEDDING_MODEL_PATTERNS)


def _as_bool(value: Optional[str], default: bool) -> bool:
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def create_app() -> Flask:
    setup_logging()
    from backend.agent.document_store import DocumentStore
    from backend.agent.frontier_store import FrontierStore
    from backend.agent.runtime import AgentRuntime, CrawlFetcher
    from backend.app.services.vector_index import VectorIndexService
    from engine.indexing.crawl import CrawlClient

    from engine.config import EngineConfig

    from .api import agent_tools as agent_tools_api
    from .api import agent_logs as agent_logs_api
    from .api import agent_browser as agent_browser_api
    from .api import chat as chat_api
    from .api import discovery as discovery_api
    from .api import extract as extract_api
    from .api import browser as browser_api
    from .api import progress as progress_api
    from .api import visits as visits_api
    from .api import docs as docs_api
    from .api import domains as domains_api
    from .api import domain_profiles as domain_profiles_api
    from .api import chat_history as chat_history_api
    from .api import memory as memory_api
    from .api import hydraflow as hydraflow_api
    from .api import llm as llm_api
    from .api import health as health_api
    from .api import diagnostics as diagnostics_api
    from .api import diagnostics_self_heal as diagnostics_self_heal_api
    from .api import roadmap as roadmap_api
    from .api import dev_diag as dev_diag_api
    from .api import db as db_api
    from .api import self_heal as self_heal_api
    from .api import self_heal_execute as self_heal_execute_api
    from .api import shipit_diag as shipit_diag_api
    from .api import index as index_api
    from .api import index_health as index_health_api
    from .api import jobs as jobs_api
    from .api import metrics as metrics_api
    from .api import admin as admin_api
    from .api import meta as meta_api
    from .api import refresh as refresh_api
    from .api import plan as plan_api
    from .api import shadow as shadow_api
    from .api import research as research_api
    from .api import reasoning as reasoning_api
    from .api import web_search as web_search_api
    from .api import seeds as seeds_api
    from .api import search as search_api
    from .api import shipit_crawl as shipit_crawl_api
    from .api import shipit_history as shipit_history_api
    from .api import shipit_ingest as shipit_ingest_api
    from .api import system_check as system_check_api
    from .api import sources as sources_api
    from .api import runtime as runtime_api
    from .api import embeddings as embeddings_api
    # Config routes (persisted app configuration)
    from .routes import config as config_routes
    from .config import AppConfig
    from .embedding_manager import EmbeddingManager
    from .jobs.focused_crawl import FocusedCrawlManager
    from .middleware import request_id as request_id_middleware
    from .jobs.runner import JobRunner
    from backend.app.db.store import AppStateDB
    from backend.app.services.progress_bus import ProgressBus
    from backend.app.services.log_bus import AgentLogBus
    from backend.app.services.incident_log import IncidentLog
    from backend.app.search.service import SearchService
    from server.learned_web_db import get_db as get_learned_web_db
    from server.refresh_worker import RefreshWorker
    from backend.app.services.labeler import LabelWorker, MemoryAgingWorker
    from backend.app.shadow.policy_store import ShadowPolicyStore
    from backend.app.shadow.capture import ShadowCaptureService
    from backend.app.shadow.manager import ShadowIndexer

    # ==========================================================================
    # App initialization
    # ==========================================================================

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

    CORS(
        app,
        resources={
            r"/api/*": {
                "origins": ["http://localhost:3100", "http://127.0.0.1:3100", "app://renderer"],
            }
        },
        supports_credentials=True,
    )

    @app.before_request
    def _api_only_gate():
        path = request.path or ""
        if path == "/" or path.startswith("/api/") or request.endpoint:
            return None
        return (
            jsonify({"error": "Not Found", "hint": "UI served from frontend at :3100"}),
            404,
        )

    @app.get("/health")
    def health() -> Response:
        return jsonify({"ok": True}), 200

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

    @app.post("/api/logs")
    def ingest_logs() -> Response:
        """Ingest logs from frontend/electron and persist to the shared telemetry store.

        This endpoint accepts a JSON payload (single object or array of objects).
        It's intentionally permissive; values are redacted and normalized before
        being written using the standard telemetry writer.
        """

        if not request.is_json:
            return jsonify({"ok": False, "reason": "expected json"}), 400

        try:
            payload = request.get_json(silent=True)
        except Exception:
            return jsonify({"ok": False, "reason": "invalid json"}), 400

        # Basic local rate-limiting to prevent noisy clients from spamming the
        # telemetry store. This is intentionally lightweight and in-memory only.
        try:
            from .rate_limiter import allow_for_remote_addr

            remote = request.remote_addr
            if not allow_for_remote_addr(remote):
                return jsonify({"ok": False, "reason": "rate_limited"}), 429
        except Exception:
            # best-effort: if the limiter fails, allow the request
            pass

        from backend import logging_utils as _logging_utils
        from server.json_logger import log_event as _log_event

        def _handle_one(obj: dict) -> None:
            if not isinstance(obj, dict):
                return
            # Ensure known top-level fields
            level = str(obj.get("level", obj.get("lvl", "INFO"))).upper()
            event = str(obj.get("event", obj.get("evt", obj.get("type", "ui.log"))))
            msg = obj.get("msg") or obj.get("message") or obj.get("m") or None
            meta = obj.get("meta") or obj.get("data") or None
            # feature and component hints (top-level fields used by logger)
            feature = obj.get("feature") or obj.get("feat") or None
            component = obj.get("component") or obj.get("comp") or None
            source = obj.get("source") or obj.get("src") or "ui"
            test_run_id = (
                obj.get("test_run_id")
                or obj.get("tr")
                or request.headers.get("x-test-run-id")
            )
            # Redact noisy/sensitive fields
            if isinstance(meta, dict):
                meta = _logging_utils.redact(meta)
            # Funnel into existing server-side structured event writer
            try:
                _log_event(
                    level,
                    event,
                    msg=msg,
                    meta=meta,
                    source=source,
                    feature=feature,
                    component=component,
                    test_run_id=test_run_id,
                )
            except Exception:
                # best-effort, don't surface internal errors to the client
                _logging_utils.write_event({"level": "ERROR", "event": "logs.ingest.error", "msg": "failed to write ui log"})

        if isinstance(payload, list):
            for item in payload:
                _handle_one(item)
        elif isinstance(payload, dict):
            _handle_one(payload)
        else:
            return jsonify({"ok": False, "reason": "unexpected payload"}), 400

        return jsonify({"ok": True}), 200

    @app.get("/api/logs/recent")
    def recent_logs() -> Response:
        """Return the most recent telemetry events as JSON array.

        Query params:
        - n: number of entries (default 100)
        """

        try:
            n = int(request.args.get("n", "100"))
        except Exception:
            n = 100

        from backend import logging_utils as _logging_utils

        log_dir = os.getenv("LOG_DIR", "data/telemetry")
        # Optional feature param to read from per-feature logs
        feature = request.args.get("feature") or request.args.get("feat")
        if feature:
            path = os.path.join(log_dir, feature, "events.ndjson")
            # if daily files are used, prefer today's date if exists
            day = datetime.utcnow().date().isoformat()
            alt = os.path.join(log_dir, feature, f"{day}.ndjson")
            if os.path.exists(alt):
                path = alt
        else:
            path = os.path.join(log_dir, "events.ndjson")
        out = []
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as handle:
                    # read tail efficiently by reading last chunk
                    data = handle.read()
                    lines = [l for l in data.splitlines() if l.strip()]
                    for line in lines[-n:]:
                        try:
                            out.append(json.loads(line))
                        except Exception:
                            out.append({"raw": line})
        except Exception:
            return jsonify({"ok": False, "reason": "read_error"}), 500

        return jsonify({"ok": True, "entries": out}), 200

    config = AppConfig.from_env()
    config.ensure_dirs()
    config.log_summary()

    # App state database
    # --------------------------------------------------------------------------
    state_db = AppStateDB(config.app_state_db_path)
    progress_bus = ProgressBus()
    agent_log_bus = AgentLogBus()
    incident_log = IncidentLog()
    app.config["APP_STATE_DB"] = state_db
    app.config["PROGRESS_BUS"] = progress_bus
    app.config["AGENT_LOG_BUS"] = agent_log_bus
    app.config["INCIDENT_LOG"] = incident_log

    # --------------------------------------------------------------------------
    # Learned web database
    # --------------------------------------------------------------------------
    db = get_learned_web_db(config.learned_web_db_path)
    app.config["DB"] = db

    # --------------------------------------------------------------------------
    # RAG components
    # --------------------------------------------------------------------------
    rag_enabled = _as_bool(os.getenv("RAG_ENABLED"), default=False)
    rag_model_primary = os.getenv("RAG_MODEL_PRIMARY", "gpt-oss").strip()
    rag_model_fallback = os.getenv("RAG_MODEL_FALLBACK", "").strip() or None
    rag_model_embed = os.getenv("RAG_MODEL_EMBED", "embeddinggemma").strip()

    engine_config = EngineConfig.from_yaml(CONFIG_PATH)
    app.config.setdefault("RAG_ENGINE_CONFIG", engine_config)

    chat_logger = logging.getLogger("backend.app.api.chat")
    chat_logger.setLevel(config.chat_log_level)
    chat_logger.propagate = True
    app.config.setdefault("CHAT_LOGGER", chat_logger)

    db = get_learned_web_db(config.learned_web_db_path)
    runner = JobRunner(config.logs_dir, worker_count=3)
    manager = FocusedCrawlManager(
        config,
        runner,
        db,
        state_db=state_db,
        progress_bus=progress_bus,
        agent_log_bus=agent_log_bus,
    )
    search_service = SearchService(config, manager)
    refresh_worker = RefreshWorker(
        config,
        search_service=search_service,
        db=db,
        state_db=state_db,
        progress_bus=progress_bus,
    )

    documents_dir = config.agent_data_dir / "documents"
    frontier_store = FrontierStore(config.frontier_db_path)
    document_store = DocumentStore(documents_dir)
    vector_index_service = VectorIndexService(
        engine_config=engine_config,
        app_config=config,
        state_db=state_db,
    )
    def _record_domain_clearance(response, html):
        try:
            from backend.app.services.auth_clearance import detect_clearance

            detect_clearance(response, html, url=getattr(response, "url", None))
        except Exception:  # pragma: no cover - detection best effort
            LOGGER.debug("auth clearance detection failed", exc_info=True)

    crawler_client = CrawlClient(
        user_agent=os.getenv("AGENT_USER_AGENT", "SelfHostedSearchAgent/0.1"),
        request_timeout=float(os.getenv("AGENT_REQUEST_TIMEOUT", "15")),
        read_timeout=float(os.getenv("AGENT_READ_TIMEOUT", "30")),
        min_delay=float(os.getenv("AGENT_MIN_DELAY", "1.0")),
        clearance_callback=_record_domain_clearance,
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

    agent_browser_enabled = _as_bool(os.getenv("AGENT_BROWSER_ENABLED"), feature_agent_mode)
    agent_browser_headless = _as_bool(os.getenv("AGENT_BROWSER_HEADLESS"), True)
    try:
        agent_browser_timeout = int(os.getenv("AGENT_BROWSER_DEFAULT_TIMEOUT_S", "15"))
    except (TypeError, ValueError):
        agent_browser_timeout = 15
    try:
        agent_browser_action_timeout_ms = int(os.getenv("AGENT_BROWSER_ACTION_TIMEOUT_MS", "5000"))
    except (TypeError, ValueError):
        agent_browser_action_timeout_ms = 5_000
    try:
        agent_browser_navigation_timeout_ms = int(os.getenv("AGENT_BROWSER_NAV_TIMEOUT_MS", "15000"))
    except (TypeError, ValueError):
        agent_browser_navigation_timeout_ms = 15_000
    try:
        agent_browser_idle_timeout = float(os.getenv("AGENT_BROWSER_IDLE_TIMEOUT_S", "120"))
    except (TypeError, ValueError):
        agent_browser_idle_timeout = 120.0
    try:
        agent_browser_max_retries = int(os.getenv("AGENT_BROWSER_MAX_RETRIES", "1"))
    except (TypeError, ValueError):
        agent_browser_max_retries = 1
    agent_browser_prewarm = _as_bool(os.getenv("AGENT_BROWSER_PREWARM"), False)

    app.config.setdefault("AGENT_BROWSER_ENABLED", agent_browser_enabled)
    app.config.setdefault("AGENT_BROWSER_HEADLESS", agent_browser_headless)
    app.config.setdefault("AGENT_BROWSER_DEFAULT_TIMEOUT_S", agent_browser_timeout)
    app.config.setdefault("AGENT_BROWSER_ACTION_TIMEOUT_MS", agent_browser_action_timeout_ms)
    app.config.setdefault("AGENT_BROWSER_NAV_TIMEOUT_MS", agent_browser_navigation_timeout_ms)
    app.config.setdefault("AGENT_BROWSER_IDLE_TIMEOUT_S", agent_browser_idle_timeout)
    app.config.setdefault("AGENT_BROWSER_MAX_RETRIES", agent_browser_max_retries)
    app.config.setdefault("AGENT_BROWSER_PREWARM", agent_browser_prewarm)
    app.config.setdefault("AGENT_BROWSER_MANAGER", None)

    if app.config["AGENT_BROWSER_ENABLED"] and app.config["AGENT_BROWSER_PREWARM"]:
        try:
            from .services.agent_browser import AgentBrowserManager

            browser_manager = AgentBrowserManager(
                default_timeout_s=app.config["AGENT_BROWSER_DEFAULT_TIMEOUT_S"],
                headless=app.config["AGENT_BROWSER_HEADLESS"],
                idle_timeout=app.config["AGENT_BROWSER_IDLE_TIMEOUT_S"],
                action_timeout_ms=app.config["AGENT_BROWSER_ACTION_TIMEOUT_MS"],
                navigation_timeout_ms=app.config["AGENT_BROWSER_NAV_TIMEOUT_MS"],
                max_retries=app.config["AGENT_BROWSER_MAX_RETRIES"],
            )
        except Exception:  # pragma: no cover - defensive logging
            LOGGER.exception("Agent browser prewarm failed")
        else:
            app.config["AGENT_BROWSER_MANAGER"] = browser_manager
            try:
                browser_manager.health()
            except Exception:  # pragma: no cover - defensive logging
                LOGGER.exception("Agent browser health check failed after prewarm")

    feature_local_discovery = (
        os.getenv("FEATURE_LOCAL_DISCOVERY", "0").lower() in {"1", "true", "yes", "on"}
    )
    app.config.setdefault("FEATURE_LOCAL_DISCOVERY", feature_local_discovery)

    reload_enabled = os.getenv("BACKEND_RELOAD", "0").lower() in {"1", "true", "yes", "on"}

    label_worker = None
    memory_worker = None
    try:
        worker_interval = float(os.getenv("LABELER_INTERVAL", "600"))
    except (TypeError, ValueError):
        worker_interval = 600.0
    try:
        memory_interval = float(os.getenv("MEMORY_AGING_INTERVAL", "86400"))
    except (TypeError, ValueError):
        memory_interval = 86_400.0
    should_start_workers = not reload_enabled or os.getenv("WERKZEUG_RUN_MAIN") == "true"
    if should_start_workers:
        try:
            label_worker = LabelWorker(state_db, interval=worker_interval)
            memory_worker = MemoryAgingWorker(state_db, interval=memory_interval)
            label_worker.start()
            memory_worker.start()
        except Exception:  # pragma: no cover - defensive logging
            LOGGER.exception("background enrichment workers failed to start")
            label_worker = None
            memory_worker = None
        else:
            import atexit

            atexit.register(label_worker.stop)
            atexit.register(memory_worker.stop)

    app.config.setdefault("LABEL_WORKER", label_worker)
    app.config.setdefault("MEMORY_AGING_WORKER", memory_worker)

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

    from backend.app.services.pending_vector_worker import PendingVectorWorker

    vector_pending_worker: PendingVectorWorker | None = None
    try:
        vector_pending_worker = PendingVectorWorker(state_db, vector_index_service)
        vector_pending_worker.start()
    except Exception:  # pragma: no cover - defensive guard
        LOGGER.exception("pending vector worker failed to start")
        vector_pending_worker = None
    else:
        import atexit

        atexit.register(vector_pending_worker.stop)

    threading.Thread(target=vector_index_service.warmup, name="embed-warmup", daemon=True).start()

    app.config.update(
        APP_CONFIG=config,
        JOB_RUNNER=runner,
        FOCUSED_MANAGER=manager,
        SEARCH_SERVICE=search_service,
        REFRESH_WORKER=refresh_worker,
        LEARNED_WEB_DB=db,
        APP_STATE_DB=state_db,
        PROGRESS_BUS=progress_bus,
        AGENT_LOG_BUS=agent_log_bus,
        INCIDENT_LOG=incident_log,
        AGENT_RUNTIME=agent_runtime,
        VECTOR_INDEX_SERVICE=vector_index_service,
        VECTOR_PENDING_WORKER=vector_pending_worker,
    )
    feature_shadow_mode = os.getenv("FEATURE_SHADOW_MODE", "0").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    shadow_policy_store = ShadowPolicyStore(config.shadow_state_path)

    shadow_capture_service = ShadowCaptureService(
        app=app,
        policy_store=shadow_policy_store,
        vector_index=vector_index_service,
        config=config,
        state_db=state_db,
    )

    shadow_manager = ShadowIndexer(
        app=app,
        runner=runner,
        vector_index=vector_index_service,
        state_db=state_db,
        enabled=feature_shadow_mode,
    )
    app.config.setdefault("SHADOW_POLICY_STORE", shadow_policy_store)
    app.config.setdefault("SHADOW_CAPTURE_SERVICE", shadow_capture_service)
    app.config.setdefault("SHADOW_INDEX_MANAGER", shadow_manager)
    app.config.setdefault("FEATURE_SHADOW_MODE", feature_shadow_mode)
    app.config.setdefault(
        "SEED_REGISTRY_PATH",
        Path(__file__).resolve().parents[2] / "seeds" / "registry.yaml",
    )
    app.config.setdefault("SEED_WORKSPACE_DIRECTORY", "workspace")

    from .api._shipit_jobs import SimulatedJobStore

    app.config.setdefault("SHIPIT_JOB_STORE", SimulatedJobStore())
    app.config.setdefault("SHIPIT_HISTORY", deque(maxlen=100))
    app.config.setdefault("SHIPIT_HISTORY_LOCK", threading.Lock())
    app.config.setdefault("SHIPIT_MEMORY", [])
    app.config.setdefault("SHIPIT_MEMORY_LOCK", threading.Lock())

    app.register_blueprint(search_api.bp)
    app.register_blueprint(jobs_api.bp)
    app.register_blueprint(progress_api.bp)
    app.register_blueprint(agent_logs_api.bp)
    app.register_blueprint(visits_api.bp)
    app.register_blueprint(docs_api.bp)
    app.register_blueprint(domains_api.bp)
    app.register_blueprint(domain_profiles_api.bp)
    app.register_blueprint(memory_api.bp)
    app.register_blueprint(hydraflow_api.bp)
    app.register_blueprint(chat_history_api.bp)
    app.register_blueprint(chat_api.bp)
    app.register_blueprint(reasoning_api.bp)
    app.register_blueprint(llm_api.bp)
    app.register_blueprint(health_api.bp)
    app.register_blueprint(research_api.bp)
    app.register_blueprint(web_search_api.bp)
    app.register_blueprint(diagnostics_api.bp)
    app.register_blueprint(diagnostics_self_heal_api.bp)
    app.register_blueprint(roadmap_api.bp)
    app.register_blueprint(dev_diag_api.bp)
    app.register_blueprint(db_api.bp)
    app.register_blueprint(self_heal_api.bp)
    app.register_blueprint(self_heal_execute_api.bp)
    app.register_blueprint(shipit_diag_api.bp)
    app.register_blueprint(metrics_api.bp)
    app.register_blueprint(meta_api.bp)
    app.register_blueprint(admin_api.bp)
    app.register_blueprint(refresh_api.bp)
    app.register_blueprint(plan_api.bp)
    app.register_blueprint(agent_tools_api.bp)
    # Register simple crawl utilities used by tests
    from .api import crawl as crawl_api
    app.register_blueprint(crawl_api.bp)
    app.register_blueprint(browser_api.bp)
    app.register_blueprint(seeds_api.bp)
    app.register_blueprint(extract_api.bp)
    app.register_blueprint(index_api.bp)
    app.register_blueprint(index_health_api.bp)
    app.register_blueprint(discovery_api.bp)
    app.register_blueprint(embeddings_api.bp)
    app.register_blueprint(shadow_api.bp)
    app.register_blueprint(shipit_crawl_api.bp)
    app.register_blueprint(shipit_history_api.bp)
    app.register_blueprint(shipit_ingest_api.bp)
    app.register_blueprint(system_check_api.bp)
    app.register_blueprint(sources_api.bp)
    app.register_blueprint(runtime_api.bp)
    app.register_blueprint(config_routes.bp)

    app.before_request(request_id_middleware.before_request)
    app.after_request(request_id_middleware.after_request)

    @app.route("/api/health")
    def health_check():
        return jsonify({"status": "ok"})

    # Back-compat liveness endpoint used by tests
    @app.route("/api/healthz")
    def healthz():
        return jsonify({"status": "ok"})

    # Minimal root route used by diagnostics template test
    @app.get("/")
    def index_root():
        try:
            return render_template("index.html")
        except Exception:
            # Fallback JSON to keep API-only deployments responsive
            return jsonify({"ok": True, "diagnostics_controls": True}), 200

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

    return app
