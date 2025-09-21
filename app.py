"""Entry point exposing the Flask application."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

from backend.app import create_app
from engine.agents.rag import RagAgent
from engine.config import EngineConfig
from engine.data.store import VectorStore
from engine.indexing.coldstart import ColdStartIndexer
from engine.indexing.crawl import CrawlClient
from engine.indexing.chunk import TokenChunker
from engine.indexing.embed import OllamaEmbedder
from engine.search.provider import seed_urls_for_query
from engine.llm.ollama_client import OllamaClient
from llm.seed_guesser import guess_urls as llm_guess_urls

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
vector_store = VectorStore(ENGINE_CONFIG.index.persist_dir, ENGINE_CONFIG.index.db_path)
chunker = TokenChunker()
crawler = CrawlClient(
    user_agent=ENGINE_CONFIG.crawl.user_agent,
    request_timeout=ENGINE_CONFIG.crawl.request_timeout,
    read_timeout=ENGINE_CONFIG.crawl.read_timeout,
    min_delay=ENGINE_CONFIG.crawl.sleep_seconds,
)


def _llm_seed_provider(query: str, limit: int, model: str | None) -> list[str]:
    urls = llm_guess_urls(query, model=model)
    return urls[:limit] if limit > 0 else urls


coldstart = ColdStartIndexer(
    store=vector_store,
    crawler=crawler,
    chunker=chunker,
    embedder=embedder,
    seed_provider=seed_urls_for_query,
    llm_seed_provider=_llm_seed_provider,
    max_pages=ENGINE_CONFIG.crawl.max_pages,
)
rag_agent = RagAgent(
    client=ollama_client,
    primary_model=ENGINE_CONFIG.models.llm_primary,
    fallback_model=ENGINE_CONFIG.models.llm_fallback,
)

app = create_app()
embedding_ready = ollama_client.has_model(embed_model_name)
if not embedding_ready:
    logging.getLogger(__name__).warning(
        "Ollama embedding model '%s' unavailable at %s. Semantic search will be disabled until installed.",
        embed_model_name,
        ENGINE_CONFIG.ollama.base_url,
    )
app.config.update(
    RAG_ENGINE_CONFIG=ENGINE_CONFIG,
    RAG_VECTOR_STORE=vector_store,
    RAG_EMBEDDER=embedder,
    RAG_COLDSTART=coldstart,
    RAG_AGENT=rag_agent,
    RAG_EMBEDDING_READY=embedding_ready,
    RAG_EMBED_MODEL_NAME=embed_model_name,
    RAG_OLLAMA_HOST=ENGINE_CONFIG.ollama.base_url,
)


if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    app.run(debug=True)
