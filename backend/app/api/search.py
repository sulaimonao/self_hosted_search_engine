"""Search API blueprint."""

from __future__ import annotations

import textwrap
import time
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import urlunparse

from flask import Blueprint, current_app, g, jsonify, request
from markupsafe import escape

from engine.agents.rag import RagAgent
from engine.agents.rag import RagResult
from engine.config import EngineConfig
from engine.data.store import VectorStore
from engine.indexing.embed import EmbeddingError, OllamaEmbedder
from engine.indexing.coldstart import ColdStartIndexer
from engine.llm.ollama_client import OllamaClientError
from backend.app.embedding_manager import EmbeddingManager
from backend.app.api.seeds import parse_http_url
from backend.logging_utils import event_base, redact, write_event
from server.llm import LLMError
from server.runlog import add_run_log_line, current_run_log

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


def _embedding_unavailable_payload(
    message: str, *, status: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    embed_config_name = current_app.config.get("RAG_EMBED_MODEL_NAME")
    host = current_app.config.get("RAG_OLLAMA_HOST")
    status_model = (status or {}).get("model") if status else None
    target_model = status_model or embed_config_name or "embeddinggemma"
    action = f"ollama pull {target_model}" if target_model else None
    payload = {
        "status": "warming",
        "error": "Embedding model unavailable",
        "detail": message,
        "code": _EMBEDDING_ERROR_CODE,
        "model": target_model,
        "host": host,
        "candidates": [],
    }
    if action:
        payload["action"] = action
    if status:
        payload["embedder_status"] = status
        if status.get("fallbacks"):
            payload["fallbacks"] = status.get("fallbacks")
    return payload


def _embedding_unavailable_response(message: str, *, status: dict | None = None) -> tuple:
    payload = _embedding_unavailable_payload(message, status=status)
    return jsonify(payload), 200


def _warming_payload(
    detail: str,
    *,
    code: str = "warming",
    candidates: Sequence[Mapping[str, Any]] | None = None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": "warming",
        "detail": detail,
        "code": code,
        "candidates": list(candidates or []),
    }
    if extra:
        payload.update({str(k): v for k, v in extra.items()})
    return payload


def _ensure_embedder_ready(
    embed_manager: EmbeddingManager | None,
    embedder: OllamaEmbedder,
    embed_model_name: str,
) -> tuple[bool, str, Mapping[str, Any] | None, str | None]:
    if embed_manager is None:
        return True, embed_model_name, None, None
    try:
        status = embed_manager.wait_until_ready()
    except Exception as exc:  # pragma: no cover - defensive logging
        current_app.logger.debug("embed manager readiness check failed", exc_info=True)
        return False, embed_model_name, None, str(exc)
    status = status or {}
    state = status.get("state") if isinstance(status, Mapping) else None
    if state != "ready":
        detail = None
        if isinstance(status, Mapping):
            detail = status.get("detail") or status.get("error")
        if not detail:
            detail = "Embedding model is warming up."
        return False, embed_model_name, status, detail
    active_model = (
        status.get("model") if isinstance(status, Mapping) else embed_model_name
    ) or embed_model_name
    if active_model:
        try:
            embedder.set_model(active_model)
            embed_model_name = active_model
        except Exception:  # pragma: no cover - defensive logging
            current_app.logger.debug(
                "failed to update embedder model to %s", active_model, exc_info=True
            )
    return True, embed_model_name, status, None


def _float_or_zero(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _collect_candidates_from_steps(
    steps: Sequence[Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    if not steps:
        return []
    seen: dict[str, dict[str, Any]] = {}
    aggregated: list[dict[str, Any]] = []
    for step in steps:
        if not isinstance(step, Mapping):
            continue
        tool_payload = step.get("tool")
        if not isinstance(tool_payload, Mapping):
            continue
        if not tool_payload.get("ok"):
            continue
        tool_name = str(tool_payload.get("tool") or "")
        result = tool_payload.get("result")
        if not isinstance(result, Mapping):
            continue
        if tool_name == "index.search":
            hits = result.get("results")
            if not isinstance(hits, Sequence):
                continue
            for raw in hits:
                if not isinstance(raw, Mapping):
                    continue
                url = raw.get("url")
                if not isinstance(url, str) or not url or url in seen:
                    continue
                candidate = {
                    "url": url,
                    "title": raw.get("title") or url,
                    "snippet": _format_snippet(str(raw.get("text", ""))),
                    "score": _float_or_zero(
                        raw.get("similarity") or raw.get("score")
                    ),
                    "source": tool_name,
                }
                seen[url] = candidate
                aggregated.append(candidate)
        elif tool_name == "crawl.fetch":
            url = result.get("url")
            if not isinstance(url, str) or not url or url in seen:
                continue
            candidate = {
                "url": url,
                "title": result.get("title") or url,
                "snippet": _format_snippet(str(result.get("text", ""))),
                "score": _float_or_zero(result.get("score")),
                "source": tool_name,
            }
            status_code = result.get("status_code")
            if isinstance(status_code, int):
                candidate["status_code"] = status_code
            seen[url] = candidate
            aggregated.append(candidate)
    return aggregated


def _summarize_tool_steps(steps: Sequence[Mapping[str, Any]] | None) -> list[str]:
    summaries: list[str] = []
    if not steps:
        return summaries
    for step in steps:
        if not isinstance(step, Mapping):
            continue
        tool_payload = step.get("tool")
        if not isinstance(tool_payload, Mapping):
            continue
        iteration = step.get("iteration") if isinstance(step.get("iteration"), int) else None
        tool_name = str(tool_payload.get("tool") or "tool")
        prefix = f"{iteration}:{tool_name}" if iteration is not None else tool_name
        if tool_payload.get("ok"):
            result = tool_payload.get("result")
            detail = "ok"
            if isinstance(result, Mapping):
                if tool_name == "index.search":
                    hits = result.get("results")
                    count = len(hits) if isinstance(hits, Sequence) else 0
                    detail = f"hits={count}"
                elif tool_name == "crawl.fetch":
                    status_code = result.get("status_code")
                    if isinstance(status_code, int):
                        detail = f"status={status_code}"
            summaries.append(f"{prefix} {detail}")
        else:
            error = tool_payload.get("error")
            detail = str(error) if error else "error"
            summaries.append(f"{prefix} {detail}")
    return summaries


def run_agent(
    query: str,
    *,
    model: str | None = None,
    context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    start = time.time()
    route = f"{request.method} {request.path}" if request else "agent"
    request_id = getattr(g, "request_id", None)
    session_id = getattr(g, "session_id", None)
    user_id = getattr(g, "user_id", None)
    add_run_log_line(f"agent turn: {query[:80]}")

    def _finalize(payload: dict[str, Any], *, status: str, message: str) -> dict[str, Any]:
        if status == "ok":
            add_run_log_line("agent turn complete")
        else:
            add_run_log_line(f"agent status={status}")
        response_payload = dict(payload)
        run_log = current_run_log()
        if run_log is not None and "run_log" not in response_payload:
            response_payload["run_log"] = run_log.dump()
        meta_payload = dict(response_payload)
        if isinstance(meta_payload.get("run_log"), list):
            meta_payload["run_log"] = len(meta_payload["run_log"])
        meta = {
            "query": query,
            "model_requested": model,
            "response": meta_payload,
        }
        duration_ms = int((time.time() - start) * 1000)
        write_event(
            event_base(
                event="agent.turn",
                level="INFO" if status == "ok" else "ERROR",
                status=status,
                route=route,
                request_id=request_id,
                session_id=session_id,
                user_id=user_id,
                duration_ms=duration_ms,
                msg=message,
                meta=meta,
            )
        )
        return response_payload

    planner = current_app.config.get("RAG_PLANNER_AGENT")
    if planner is None:
        payload = _warming_payload(
            "Planner agent unavailable.",
            code="planner_unavailable",
            candidates=[],
        )
        payload["llm_used"] = True
        if model:
            payload["llm_model"] = model
        return _finalize(payload, status="error", message="planner unavailable")

    engine_config: EngineConfig | None = current_app.config.get("RAG_ENGINE_CONFIG")
    embedder: OllamaEmbedder | None = current_app.config.get("RAG_EMBEDDER")
    embed_manager: EmbeddingManager | None = current_app.config.get("RAG_EMBED_MANAGER")
    embed_model_name = (
        current_app.config.get("RAG_EMBED_MODEL_NAME")
        if current_app.config.get("RAG_EMBED_MODEL_NAME")
        else (engine_config.models.embed if engine_config else None)
    ) or "embeddinggemma"

    if embedder is None:
        payload = _warming_payload(
            "Embedding pipeline unavailable.",
            code="embedder_unavailable",
            candidates=[],
        )
        payload["llm_used"] = True
        if model:
            payload["llm_model"] = model
        return _finalize(payload, status="error", message="embedder unavailable")

    ready, _, status, detail = _ensure_embedder_ready(
        embed_manager, embedder, embed_model_name
    )
    if not ready:
        payload = _embedding_unavailable_payload(detail or "Embedding model unavailable.", status=status)
        payload["llm_used"] = True
        if model:
            payload["llm_model"] = model
        return _finalize(payload, status="error", message="embedding not ready")

    planner_context: dict[str, Any] = {}
    if engine_config is not None:
        planner_context["retrieval"] = {
            "k": engine_config.retrieval.k,
            "similarity_threshold": engine_config.retrieval.similarity_threshold,
        }
    if context:
        planner_context.update({str(k): v for k, v in context.items()})

    try:
        result = planner.run(query, context=planner_context, model=model)
    except LLMError as exc:
        message = str(exc)[:200]
        payload = {
            "type": "final",
            "answer": "Planner LLM is unavailable.",
            "sources": [],
            "actions": ["planner_unavailable"],
            "planner_model_used": None,
            "error": message,
            "planner_models": _planner_model_candidates(planner, model),
            "llm_used": True,
        }
        if model:
            payload["llm_model_requested"] = model
        return _finalize(payload, status="error", message="planner llm error")
    except Exception as exc:  # pragma: no cover - defensive logging
        current_app.logger.exception("planner execution failed for query='%s'", query)
        payload = {
            "type": "final",
            "answer": "Planner failed to complete request.",
            "sources": [],
            "actions": ["planner_error"],
            "planner_model_used": None,
            "error": str(exc)[:200],
            "planner_models": _planner_model_candidates(planner, model),
            "llm_used": True,
        }
        if model:
            payload["llm_model_requested"] = model
        return _finalize(payload, status="error", message="planner execution error")

    response = dict(result)
    used_model = response.get("planner_model_used")
    response["llm_used"] = True
    if model:
        response["llm_model_requested"] = model
    if used_model:
        response.setdefault("llm_model", used_model)
    elif model:
        response.setdefault("llm_model", model)

    steps = response.get("steps")
    candidates = _collect_candidates_from_steps(steps if isinstance(steps, Sequence) else None)
    if candidates:
        response.setdefault("candidates", candidates)
        response.setdefault("results", candidates)

    summaries = _summarize_tool_steps(steps if isinstance(steps, Sequence) else None)
    if summaries and current_app.logger.isEnabledFor(10):  # DEBUG
        current_app.logger.debug(
            "planner tool summary query='%s': %s", query, "; ".join(summaries)
        )

    return _finalize(response, status="ok", message="agent turn ok")


def _planner_model_candidates(planner: Any, requested: str | None) -> list[str]:
    candidates: list[str] = []
    if requested:
        candidates.append(requested)
    else:
        default_model = getattr(planner, "default_model", None)
        if isinstance(default_model, str) and default_model.strip():
            candidates.append(default_model.strip())
    fallback_model = getattr(planner, "fallback_model", None)
    if isinstance(fallback_model, str) and fallback_model.strip():
        cleaned = fallback_model.strip()
        if cleaned not in candidates:
            candidates.append(cleaned)
    return candidates


@bp.get("/embedder/status")
def embedder_status_endpoint():
    manager: EmbeddingManager | None = current_app.config.get("RAG_EMBED_MANAGER")
    model_name = current_app.config.get("RAG_EMBED_MODEL_NAME")
    host = current_app.config.get("RAG_OLLAMA_HOST")
    if manager is None:
        payload = {
            "state": "unknown",
            "progress": 0,
            "model": model_name,
            "error": "manager_unavailable",
            "auto_install": False,
            "fallbacks": [],
            "ollama": {"base_url": host, "alive": False},
        }
        return jsonify(payload)
    status = manager.get_status(refresh=True)
    return jsonify(status)


@bp.post("/embedder/ensure")
def embedder_ensure_endpoint():
    manager: EmbeddingManager | None = current_app.config.get("RAG_EMBED_MANAGER")
    if manager is None:
        return jsonify({"error": "manager_unavailable"}), 503
    payload = request.get_json(silent=True) or {}
    requested_model = payload.get("model")
    if isinstance(requested_model, str) and requested_model.strip():
        status = manager.ensure(requested_model.strip())
    else:
        status = manager.ensure()
    return jsonify(status)


@bp.post("/crawl")
def crawl_validation_endpoint():
    payload = request.get_json(silent=True) or {}
    url_value = payload.get("url")
    if not isinstance(url_value, str) or not url_value.strip():
        return jsonify({"error": "url is required"}), 400
    try:
        parsed = parse_http_url(url_value)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    depth_value = payload.get("depth", 1)
    try:
        depth = max(1, int(depth_value))
    except (TypeError, ValueError):
        return jsonify({"error": "depth must be a positive integer"}), 400

    normalized = urlunparse((parsed.scheme, parsed.netloc, parsed.path or "", "", parsed.query, ""))
    response = {
        "url": normalized.rstrip("/"),
        "depth": depth,
        "queued": False,
        "detail": "URL validated; queue long-running crawls via /api/seeds or the Crawl Manager UI.",
    }
    return jsonify(response)


@bp.get("/search")
def search_endpoint():
    query = (request.args.get("q") or "").strip()
    if not query:
        return jsonify({"error": "Missing 'q' parameter"}), 400

    llm_enabled = _normalize_bool(request.args.get("llm"))
    llm_model = (request.args.get("model") or "").strip() or None

    if llm_enabled:
        agent_payload = run_agent(query, model=llm_model)
        return jsonify(agent_payload)

    engine_config: EngineConfig | None = current_app.config.get("RAG_ENGINE_CONFIG")
    if engine_config is None:
        search_service = current_app.config.get("SEARCH_SERVICE")
        app_config = current_app.config.get("APP_CONFIG")
        if search_service and app_config:
            results, job_id, context = search_service.run_query(
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
            if context:
                payload["confidence"] = context.get("confidence")
                if context.get("trigger_reason"):
                    payload["trigger_reason"] = context.get("trigger_reason")
                if context.get("seed_count"):
                    payload["seed_count"] = context.get("seed_count")
            if job_id:
                payload["job_id"] = job_id
                payload["last_index_time"] = search_service.last_index_time()
                if len(results) < app_config.smart_min_results or context.get("trigger_reason") == "low_confidence":
                    payload["status"] = "focused_crawl_running"
            if llm_model:
                payload["llm_model"] = llm_model
            return jsonify(payload)
        return jsonify({"error": "Semantic search unavailable"}), 503

    store: VectorStore = current_app.config["RAG_VECTOR_STORE"]
    embedder: OllamaEmbedder = current_app.config["RAG_EMBEDDER"]
    coldstart: ColdStartIndexer = current_app.config["RAG_COLDSTART"]
    rag_agent: RagAgent = current_app.config["RAG_AGENT"]
    embed_manager: EmbeddingManager | None = current_app.config.get("RAG_EMBED_MANAGER")

    embed_model_name = (
        current_app.config.get("RAG_EMBED_MODEL_NAME") or engine_config.models.embed
    )

    ready, embed_model_name, embed_status, detail = _ensure_embedder_ready(
        embed_manager, embedder, embed_model_name
    )
    if not ready:
        payload = _embedding_unavailable_payload(
            detail or "Embedding model is not ready.", status=embed_status
        )
        payload["llm_used"] = llm_enabled
        if llm_model:
            payload["llm_model"] = llm_model
        return jsonify(payload)

    try:
        query_vector = embedder.embed_query(query)
    except EmbeddingError as exc:
        message = (
            "Unable to generate embeddings from Ollama. "
            f"Ensure the model '{embed_model_name}' is installed and running."
        )
        payload = _embedding_unavailable_payload(f"{message} ({exc})", status=embed_status)
        payload["llm_used"] = llm_enabled
        if llm_model:
            payload["llm_model"] = llm_model
        return jsonify(payload)
    except Exception as exc:  # pragma: no cover - defensive logging
        current_app.logger.debug("unexpected embedding failure", exc_info=True)
        payload = _warming_payload(
            "Unable to embed query.",
            code="embedding_failure",
            extra={"error": str(exc), "model": embed_model_name},
        )
        payload["llm_used"] = llm_enabled
        if llm_model:
            payload["llm_model"] = llm_model
        return jsonify(payload)

    try:
        results = store.query(
            vector=query_vector,
            k=engine_config.retrieval.k,
            similarity_threshold=engine_config.retrieval.similarity_threshold,
        )
    except Exception as exc:
        current_app.logger.debug("vector store query failed", exc_info=True)
        payload = _warming_payload(
            "Vector store warming up.",
            code="vector_store_unavailable",
            extra={"error": str(exc)},
        )
        payload["llm_used"] = llm_enabled
        payload["results"] = []
        if llm_model:
            payload["llm_model"] = llm_model
        return jsonify(payload)

    if len(results) < engine_config.retrieval.min_hits:
        try:
            coldstart.build_index(query, use_llm=llm_enabled, llm_model=llm_model)
        except Exception as exc:  # pragma: no cover - defensive logging
            current_app.logger.debug("coldstart build failed", exc_info=True)
            payload = _warming_payload(
                "Focused crawl warming up.",
                code="coldstart_unavailable",
                extra={"error": str(exc)},
            )
            payload["llm_used"] = llm_enabled
            payload["results"] = [_serialize_chunk(chunk) for chunk in results]
            if llm_model:
                payload["llm_model"] = llm_model
            return jsonify(payload)
        try:
            query_vector = embedder.embed_query(query)
        except EmbeddingError as exc:
            message = (
                "Unable to generate embeddings from Ollama. "
                f"Ensure the model '{embed_model_name}' is installed and running."
            )
            payload = _embedding_unavailable_payload(
                f"{message} ({exc})", status=embed_status
            )
            payload["llm_used"] = llm_enabled
            if llm_model:
                payload["llm_model"] = llm_model
            return jsonify(payload)
        except Exception as exc:  # pragma: no cover - defensive logging
            current_app.logger.debug("unexpected embedding failure after coldstart", exc_info=True)
            payload = _warming_payload(
                "Unable to embed query after coldstart.",
                code="embedding_failure",
                extra={"error": str(exc), "model": embed_model_name},
            )
            payload["llm_used"] = llm_enabled
            if llm_model:
                payload["llm_model"] = llm_model
            return jsonify(payload)
        try:
            results = store.query(
                vector=query_vector,
                k=engine_config.retrieval.k,
                similarity_threshold=engine_config.retrieval.similarity_threshold,
            )
        except Exception as exc:
            current_app.logger.debug("vector store query failed after coldstart", exc_info=True)
            payload = _warming_payload(
                "Vector store warming up.",
                code="vector_store_unavailable",
                extra={"error": str(exc)},
            )
            payload["llm_used"] = llm_enabled
            payload["results"] = []
            if llm_model:
                payload["llm_model"] = llm_model
            return jsonify(payload)

    serialized_results = [_serialize_chunk(chunk) for chunk in results]

    if not results:
        payload = {
            "status": "no_results",
            "answer": "I could not find relevant information in the local index.",
            "sources": [],
            "k": 0,
            "results": serialized_results,
            "llm_used": llm_enabled,
        }
        payload["hits"] = serialized_results
        if llm_model:
            payload["llm_model"] = llm_model
        return jsonify(payload)

    if not llm_enabled:
        payload = {
            "status": "ok_no_llm",
            "answer": "",
            "sources": [],
            "k": len(serialized_results),
            "results": serialized_results,
            "llm_used": False,
        }
        payload["hits"] = serialized_results
        if llm_model:
            payload["llm_model"] = llm_model
        return jsonify(payload)

    try:
        rag_result: RagResult = rag_agent.run(query, results)
    except OllamaClientError as exc:
        payload = {
            "status": "ok",
            "code": "rag_error",
            "detail": f"Failed to generate answer: {exc}",
            "answer": "",
            "sources": [],
            "k": 0,
            "results": serialized_results,
            "llm_used": llm_enabled,
        }
        payload["hits"] = serialized_results
        if llm_model:
            payload["llm_model"] = llm_model
        return jsonify(payload)
    except Exception as exc:  # pragma: no cover - defensive logging
        current_app.logger.debug("rag agent failed", exc_info=True)
        payload = {
            "status": "ok",
            "code": "rag_error",
            "detail": "Answer generation warming up.",
            "error": str(exc),
            "answer": "",
            "sources": [],
            "k": 0,
            "results": serialized_results,
            "llm_used": llm_enabled,
        }
        payload["hits"] = serialized_results
        if llm_model:
            payload["llm_model"] = llm_model
        return jsonify(payload)

    payload = {
        "status": "ok",
        "answer": rag_result.answer,
        "sources": rag_result.sources,
        "k": rag_result.used,
        "results": serialized_results,
        "llm_used": llm_enabled,
    }
    payload["hits"] = serialized_results
    if llm_model:
        payload["llm_model"] = llm_model
    return jsonify(payload)
