"""Entry point exposing the Flask application."""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path

from dotenv import load_dotenv

from backend.app import create_app
from backend.app.embedding_manager import EmbeddingManager
from engine.agents.rag import RagAgent
from engine.config import EngineConfig
from engine.data.store import VectorStore
from engine.indexing.coldstart import ColdStartIndexer
from engine.indexing.crawl import CrawlClient
from engine.indexing.chunk import TokenChunker
from engine.indexing.embed import OllamaEmbedder
from engine.llm.ollama_client import OllamaClient
from llm.seed_guesser import guess_urls as llm_guess_urls
from server.discover import DiscoveryEngine
from server.learned_web_db import get_db
from server.agent import PlannerAgent
from server.llm import OllamaJSONClient
from server.tools import BrowserAPI, CrawlerAPI, EmbedAPI, IndexAPI, ToolDispatcher

load_dotenv()

CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"
ENGINE_CONFIG = EngineConfig.from_yaml(CONFIG_PATH)

_embed_override = os.getenv("RAG_EMBED_MODEL_NAME")
if _embed_override:
    logging.getLogger(__name__).info(
        "Overriding embedding model from config.yaml: using '%s'", _embed_override
    )
embed_model_name = _embed_override or ENGINE_CONFIG.models.embed

_planner_fallback_override = os.getenv("PLANNER_FALLBACK")
fallback_model_name = _planner_fallback_override or ENGINE_CONFIG.models.llm_fallback
if _planner_fallback_override:
    logging.getLogger(__name__).info(
        "Overriding planner fallback model: using '%s'", fallback_model_name
    )
elif not fallback_model_name:
    logging.getLogger(__name__).warning(
        "No planner fallback model configured; set PLANNER_FALLBACK to improve resilience"
    )

ollama_client = OllamaClient(ENGINE_CONFIG.ollama.base_url)
embedder = OllamaEmbedder(ollama_client, embed_model_name)
embed_manager = EmbeddingManager(
    base_url=ENGINE_CONFIG.ollama.base_url,
    embed_model=embed_model_name,
)
vector_store = VectorStore(ENGINE_CONFIG.index.persist_dir, ENGINE_CONFIG.index.db_path)
chunker = TokenChunker()
crawler = CrawlClient(
    user_agent=ENGINE_CONFIG.crawl.user_agent,
    request_timeout=ENGINE_CONFIG.crawl.request_timeout,
    read_timeout=ENGINE_CONFIG.crawl.read_timeout,
    min_delay=ENGINE_CONFIG.crawl.sleep_seconds,
)

discovery_engine = DiscoveryEngine()
learned_web_db = get_db()


def _llm_seed_provider(query: str, limit: int, model: str | None) -> list[str]:
    urls = llm_guess_urls(query, model=model)
    return urls[:limit] if limit > 0 else urls


coldstart = ColdStartIndexer(
    store=vector_store,
    crawler=crawler,
    chunker=chunker,
    embedder=embedder,
    discovery_engine=discovery_engine,
    learned_db=learned_web_db,
    llm_seed_provider=_llm_seed_provider,
    max_pages=ENGINE_CONFIG.crawl.max_pages,
)
rag_agent = RagAgent(
    client=ollama_client,
    primary_model=ENGINE_CONFIG.models.llm_primary,
    fallback_model=fallback_model_name,
)

planner_llm = OllamaJSONClient(
    base_url=ENGINE_CONFIG.ollama.base_url,
    default_model=ENGINE_CONFIG.models.llm_primary,
)
index_api = IndexAPI(
    store=vector_store,
    embedder=embedder,
    chunker=chunker,
    default_k=ENGINE_CONFIG.retrieval.k,
    similarity_threshold=ENGINE_CONFIG.retrieval.similarity_threshold,
)
crawler_api_adapter = CrawlerAPI(crawler)
embed_api_adapter = EmbedAPI(embedder)
tool_dispatcher = ToolDispatcher(
    index_api=index_api,
    crawler_api=crawler_api_adapter,
    embed_api=embed_api_adapter,
)
planner_agent = PlannerAgent(
    llm=planner_llm,
    tools=tool_dispatcher,
    default_model=ENGINE_CONFIG.models.llm_primary,
    fallback_model=fallback_model_name,
    max_iterations=ENGINE_CONFIG.planner.max_steps,
    enable_critique=ENGINE_CONFIG.planner.enable_critique,
    max_retries_per_step=ENGINE_CONFIG.planner.max_retries_per_step,
)

app = create_app()

testing_mode = bool(os.getenv("EMBED_TEST_MODE")) or bool(os.getenv("PYTEST_CURRENT_TEST"))
if testing_mode:
    ready_status = {
        "state": "ready",
        "progress": 100,
        "model": embed_model_name,
        "error": None,
        "detail": None,
        "auto_install": False,
        "fallbacks": [],
        "ollama": {"base_url": ENGINE_CONFIG.ollama.base_url, "alive": False},
    }

    class _TestingEmbedManager:
        def __init__(self, status: dict) -> None:
            self._status = status

        def refresh(self) -> dict:
            return dict(self._status)

        def get_status(self, *, refresh: bool = False) -> dict:  # pragma: no cover - trivial wrapper
            return dict(self._status)

        def ensure(self, preferred_model: str | None = None) -> dict:
            return dict(self._status)

        def wait_until_ready(self, timeout: float = 900.0) -> dict:
            return dict(self._status)

    embed_manager = _TestingEmbedManager(ready_status)
    initial_status = ready_status
else:
    initial_status = embed_manager.refresh()
    if initial_status.get("state") != "ready":
        logging.getLogger(__name__).warning(
            "Embedding model '%s' not ready (state=%s). Requests will trigger automatic installation.",
            initial_status.get("model"),
            initial_status.get("state"),
        )
app.config.update(
    RAG_ENGINE_CONFIG=ENGINE_CONFIG,
    RAG_VECTOR_STORE=vector_store,
    RAG_EMBEDDER=embedder,
    RAG_COLDSTART=coldstart,
    RAG_AGENT=rag_agent,
    RAG_DISCOVERY_ENGINE=discovery_engine,
    RAG_LEARNED_DB=learned_web_db,
    RAG_EMBED_MODEL_NAME=embed_model_name,
    RAG_OLLAMA_HOST=ENGINE_CONFIG.ollama.base_url,
    RAG_EMBED_MANAGER=embed_manager,
    RAG_PLANNER_LLM=planner_llm,
    RAG_INDEX_API=index_api,
    RAG_EMBED_API=embed_api_adapter,
    RAG_CRAWLER_API=crawler_api_adapter,
    RAG_PLANNER_TOOLS=tool_dispatcher,
    RAG_PLANNER_AGENT=planner_agent,
)

browser_manager = app.config.get("AGENT_BROWSER_MANAGER")
if browser_manager is not None:
    tool_dispatcher.attach_browser_api(BrowserAPI(browser_manager))


def _schedule_bootstrap_index() -> None:
    if testing_mode:
        return
    bootstrap_cfg = ENGINE_CONFIG.bootstrap
    if bootstrap_cfg is None or not bootstrap_cfg.enabled:
        return
    if not bootstrap_cfg.queries:
        logging.getLogger(__name__).info(
            "Bootstrap indexing enabled but no queries configured; skipping."
        )
        return
    try:
        if not vector_store.is_empty():
            logging.getLogger(__name__).debug(
                "Vector store already populated; skipping bootstrap indexing."
            )
            return
    except Exception:  # pragma: no cover - defensive logging only
        logging.getLogger(__name__).debug(
            "Unable to determine vector store state; skipping bootstrap indexing.",
            exc_info=True,
        )
        return

    def _run_bootstrap() -> None:
        logger = logging.getLogger(__name__)
        queries = list(bootstrap_cfg.queries)
        logger.info("Bootstrapping index with %d queries", len(queries))
        try:
            status = embed_manager.ensure(bootstrap_cfg.llm_model or embed_model_name)
        except Exception:  # pragma: no cover - defensive logging only
            logger.exception("Bootstrap failed while ensuring embedding model")
            return
        if status.get("state") != "ready":
            detail = status.get("detail") or status.get("error") or "unknown"
            logger.warning(
                "Skipping bootstrap: embedding model not ready (%s)", detail
            )
            return
        active_model = status.get("model") or embed_manager.active_model
        if active_model:
            try:
                embedder.set_model(str(active_model))
            except Exception:  # pragma: no cover - defensive logging only
                logger.exception("Failed to set embedder model during bootstrap")
                return
        for query in queries:
            try:
                count = coldstart.build_index(
                    query,
                    use_llm=bootstrap_cfg.use_llm,
                    llm_model=bootstrap_cfg.llm_model,
                )
            except Exception:  # pragma: no cover - defensive logging only
                logger.exception(
                    "Bootstrap indexing failed for query '%s'", query
                )
                continue
            logger.info(
                "Bootstrapped %d pages for query '%s'", count, query
            )

    threading.Thread(
        target=_run_bootstrap, name="bootstrap-index", daemon=True
    ).start()


_schedule_bootstrap_index()


if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    app.run(debug=True)
