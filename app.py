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
from engine.llm.ollama_client import OllamaClient

load_dotenv()

CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"
ENGINE_CONFIG = EngineConfig.from_yaml(CONFIG_PATH)

ollama_client = OllamaClient(ENGINE_CONFIG.ollama.base_url)
embedder = OllamaEmbedder(ollama_client, ENGINE_CONFIG.models.embed)
vector_store = VectorStore(ENGINE_CONFIG.index.persist_dir, ENGINE_CONFIG.index.db_path)
chunker = TokenChunker()
crawler = CrawlClient(
    user_agent=ENGINE_CONFIG.crawl.user_agent,
    request_timeout=ENGINE_CONFIG.crawl.request_timeout,
    read_timeout=ENGINE_CONFIG.crawl.read_timeout,
    min_delay=ENGINE_CONFIG.crawl.sleep_seconds,
)
coldstart = ColdStartIndexer(
    store=vector_store,
    crawler=crawler,
    chunker=chunker,
    embedder=embedder,
    max_pages=ENGINE_CONFIG.crawl.max_pages,
)
rag_agent = RagAgent(
    client=ollama_client,
    primary_model=ENGINE_CONFIG.models.llm_primary,
    fallback_model=ENGINE_CONFIG.models.llm_fallback,
)

app = create_app()
app.config.update(
    RAG_ENGINE_CONFIG=ENGINE_CONFIG,
    RAG_VECTOR_STORE=vector_store,
    RAG_EMBEDDER=embedder,
    RAG_COLDSTART=coldstart,
    RAG_AGENT=rag_agent,
)


if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    app.run(debug=True)
