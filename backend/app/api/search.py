"""Search API blueprint."""

from __future__ import annotations

import textwrap

from flask import Blueprint, current_app, jsonify, request
from markupsafe import escape

from engine.agents.rag import RagAgent
from engine.agents.rag import RagResult
from engine.config import EngineConfig
from engine.data.store import VectorStore
from engine.indexing.embed import EmbeddingError, OllamaEmbedder
from engine.indexing.coldstart import ColdStartIndexer
from engine.llm.ollama_client import OllamaClientError

bp = Blueprint("search_api", __name__, url_prefix="/api")


_EMBEDDING_ERROR_CODE = "embedding_unavailable"


def _normalize_bool(value: str | None) -> bool:
    if value is None:
        return False
    return value.lower() in {"1", "true", "on", "yes"}


def _format_snippet(text: str, width: int = 320) -> str:
    cleaned = " ".join((text or "").split())
    if not cleaned:
        return ""
    snippet = textwrap.shorten(cleaned, width=width, placeholder="…")
    return str(escape(snippet))


def _serialize_chunk(chunk: RetrievedChunk) -> dict:
    return {
        "url": chunk.url,
        "title": chunk.title,
        "snippet": _format_snippet(chunk.text),
        "score": float(chunk.similarity),
    }


def _embedding_unavailable_response(message: str) -> tuple:
    model_name = current_app.config.get("RAG_EMBED_MODEL_NAME")
    host = current_app.config.get("RAG_OLLAMA_HOST")
    action = f"ollama pull {model_name}" if model_name else None
    payload = {
        "status": _EMBEDDING_ERROR_CODE,
        "error": "Embedding model unavailable",
        "detail": message,
        "code": _EMBEDDING_ERROR_CODE,
        "model": model_name,
        "host": host,
    }
    if action:
        payload["action"] = action
    return jsonify(payload), 503


@bp.get("/search")
def search_endpoint():
    query = (request.args.get("q") or "").strip()
    if not query:
        return jsonify({"error": "Missing 'q' parameter"}), 400

    llm_enabled = _normalize_bool(request.args.get("llm"))
    llm_model = (request.args.get("model") or "").strip() or None

    engine_config: EngineConfig | None = current_app.config.get("RAG_ENGINE_CONFIG")
    if engine_config is None:
        search_service = current_app.config.get("SEARCH_SERVICE")
        app_config = current_app.config.get("APP_CONFIG")
        if search_service and app_config:
            results, job_id = search_service.run_query(
                query,
                limit=app_config.search_default_limit,
                use_llm=llm_enabled,
                model=llm_model,
            )
            payload = {
                "status": "ok",
                "results": results,
                "llm_used": bool(llm_enabled),
            }
            if job_id:
                payload.update(
                    {
                        "status": "focused_crawl_running",
                        "job_id": job_id,
                        "last_index_time": search_service.last_index_time(),
                    }
                )
            if llm_model:
                payload["llm_model"] = llm_model
            return jsonify(payload)
        return jsonify({"error": "Semantic search unavailable"}), 503

    store: VectorStore = current_app.config["RAG_VECTOR_STORE"]
    embedder: OllamaEmbedder = current_app.config["RAG_EMBEDDER"]
    coldstart: ColdStartIndexer = current_app.config["RAG_COLDSTART"]
    rag_agent: RagAgent = current_app.config["RAG_AGENT"]

    embed_model_name = (
        current_app.config.get("RAG_EMBED_MODEL_NAME") or engine_config.models.embed
    )

    if not current_app.config.get("RAG_EMBEDDING_READY", True):
        message = (
            "Semantic search requires a local embedding model. Install it with "
            f"`ollama pull {embed_model_name}` and retry."
        )
        return _embedding_unavailable_response(message)

    try:
        query_vector = embedder.embed_query(query)
    except EmbeddingError as exc:
        message = (
            "Unable to generate embeddings from Ollama. "
            f"Ensure the model '{embed_model_name}' is installed and running."
        )
        return _embedding_unavailable_response(f"{message} ({exc})")

    results = store.query(
        vector=query_vector,
        k=engine_config.retrieval.k,
        similarity_threshold=engine_config.retrieval.similarity_threshold,
    )

    if len(results) < engine_config.retrieval.min_hits:
        coldstart.build_index(query, use_llm=llm_enabled, llm_model=llm_model)
        try:
            query_vector = embedder.embed_query(query)
        except EmbeddingError as exc:
            message = (
                "Unable to generate embeddings from Ollama. "
                f"Ensure the model '{embed_model_name}' is installed and running."
            )
            return _embedding_unavailable_response(f"{message} ({exc})")
        results = store.query(
            vector=query_vector,
            k=engine_config.retrieval.k,
            similarity_threshold=engine_config.retrieval.similarity_threshold,
        )

    if not results:
        payload = {
            "status": "no_results",
            "answer": "I could not find relevant information in the local index.",
            "sources": [],
            "k": 0,
            "results": [],
            "llm_used": llm_enabled,
        }
        return jsonify(payload)

    try:
        rag_result: RagResult = rag_agent.run(query, results)
    except OllamaClientError as exc:
        return jsonify({"error": f"Failed to generate answer: {exc}"}), 502
    payload = {
        "status": "ok",
        "answer": rag_result.answer,
        "sources": rag_result.sources,
        "k": rag_result.used,
        "results": [_serialize_chunk(chunk) for chunk in results],
        "llm_used": llm_enabled,
    }
    if llm_model:
        payload["llm_model"] = llm_model
    return jsonify(payload)
