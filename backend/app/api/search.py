"""Search API blueprint."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from engine.agents.rag import RagAgent
from engine.agents.rag import RagResult
from engine.config import EngineConfig
from engine.data.store import VectorStore
from engine.indexing.embed import EmbeddingError, OllamaEmbedder
from engine.indexing.coldstart import ColdStartIndexer
from engine.llm.ollama_client import OllamaClientError

bp = Blueprint("search_api", __name__, url_prefix="/api")


@bp.get("/search")
def search_endpoint():
    query = (request.args.get("q") or "").strip()
    if not query:
        return jsonify({"error": "Missing 'q' parameter"}), 400

    engine_config: EngineConfig = current_app.config["RAG_ENGINE_CONFIG"]
    store: VectorStore = current_app.config["RAG_VECTOR_STORE"]
    embedder: OllamaEmbedder = current_app.config["RAG_EMBEDDER"]
    coldstart: ColdStartIndexer = current_app.config["RAG_COLDSTART"]
    rag_agent: RagAgent = current_app.config["RAG_AGENT"]

    try:
        query_vector = embedder.embed_query(query)
    except EmbeddingError as exc:
        return jsonify({"error": f"Failed to embed query: {exc}"}), 500

    results = store.query(
        vector=query_vector,
        k=engine_config.retrieval.k,
        similarity_threshold=engine_config.retrieval.similarity_threshold,
    )

    if len(results) < engine_config.retrieval.min_hits:
        coldstart.build_index(query)
        try:
            query_vector = embedder.embed_query(query)
        except EmbeddingError as exc:
            return jsonify({"error": f"Failed to embed query: {exc}"}), 500
        results = store.query(
            vector=query_vector,
            k=engine_config.retrieval.k,
            similarity_threshold=engine_config.retrieval.similarity_threshold,
        )

    if not results:
        return jsonify({"answer": "I could not find relevant information in the local index.", "sources": [], "k": 0})

    try:
        rag_result: RagResult = rag_agent.run(query, results)
    except OllamaClientError as exc:
        return jsonify({"error": f"Failed to generate answer: {exc}"}), 502
    return jsonify({"answer": rag_result.answer, "sources": rag_result.sources, "k": rag_result.used})
