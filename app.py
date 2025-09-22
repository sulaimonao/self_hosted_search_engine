"""Entry point exposing the Flask application."""

from __future__ import annotations

import logging
import os
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

load_dotenv()

CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"
ENGINE_CONFIG = EngineConfig.from_yaml(CONFIG_PATH)

_embed_override = os.getenv("RAG_EMBED_MODEL_NAME")
if _embed_override:
    logging.getLogger(__name__).info(
        "Overriding embedding model from config.yaml: using '%s'", _embed_override
    )
embed_model_name = _embed_override or ENGINE_CONFIG.models.embed

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
    fallback_model=ENGINE_CONFIG.models.llm_fallback,
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
)


if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    app.run(debug=True)
