"""Search API blueprint."""

from __future__ import annotations

import hashlib
import textwrap
import time
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any, cast
from urllib.parse import urlunparse

from flask import Blueprint, current_app, g, jsonify, request
from pydantic import ValidationError
from markupsafe import escape

from engine.agents.rag import RagAgent
from engine.agents.rag import RagResult
from engine.config import EngineConfig
from engine.data.store import RetrievedChunk, VectorStore
from engine.indexing.embed import EmbeddingError, OllamaEmbedder
from engine.indexing.coldstart import ColdStartIndexer
from engine.llm.ollama_client import OllamaClientError
from backend.app.embedding_manager import EmbeddingManager
from backend.app.api.seeds import parse_http_url
from backend.logging_utils import event_base, redact, write_event
from server.llm import LLMError
from server.runlog import add_run_log_line, current_run_log
from observability import start_span

from .shipit_history import append_history
from .shipit_crawl import create_crawl_job
from .schemas import SearchQueryParams, SearchResponsePayload


def _shipit_search_payload(query: str, page: int, size: int) -> tuple[int, list[dict[str, Any]], dict[str, list[list[Any]]]]:
    base_hash = hashlib.md5(query.encode("utf-8")).hexdigest()
    domain = f"{base_hash[:6]}.example.com"
    total = max(size * 4, size)
    hits: list[dict[str, Any]] = []
    topic_key = query.split()[0].lower() if query else "general"
    for index in range(size):
        rank = (page - 1) * size + index + 1
        url = f"https://{domain}/docs/{rank}"
        timestamp = datetime(2024, 1, 1, tzinfo=timezone.utc).isoformat()
        hits.append(
            {
                "id": f"{base_hash}-{rank}",
                "url": url,
                "title": f"{query.title()} Result {rank}" if query else f"Result {rank}",
                "snippet": f"Stubbed snippet for '{query}' (result {rank}).",
                "score": round(max(0.0, 1.0 - (index * 0.05)), 3),
                "topics": [topic_key] if query else [],
                "source_type": "web",
                "first_seen": timestamp,
                "last_seen": timestamp,
                "domain": domain,
            }
        )
    facets = {
        "topic": [[topic_key, total]],
        "source_type": [["web", total]],
        "domain": [[domain, total]],
        "recency": [["30d", total]],
    }
    return total, hits, facets

bp = Blueprint("search_api", __name__, url_prefix="/api")


_EMBEDDING_ERROR_CODE = "embedding_unavailable"


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

    context_keys = sorted(str(key) for key in context.keys()) if context else None

    with start_span(
        "agent.turn",
        attributes={"llm.model.requested": model or ""},
        inputs={"query": query, "context_keys": context_keys},
    ) as turn_span:

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
            if turn_span is not None:
                turn_span.set_attribute("agent.status", status)
                turn_span.set_attribute("agent.duration_ms", duration_ms)
                if isinstance(payload.get("actions"), Sequence):
                    turn_span.set_attribute("agent.actions", len(payload.get("actions", [])))
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
            payload = _embedding_unavailable_payload(
                detail or "Embedding model unavailable.", status=status
            )
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
            with start_span(
                "agent.planner.execute",
                attributes={
                    "planner.class": planner.__class__.__name__,
                    "llm.model.requested": model or "",
                },
                inputs={"query": query, "planner_context": planner_context},
            ) as planner_span:
                result = planner.run(query, context=planner_context, model=model)
                if planner_span is not None and isinstance(result, Mapping):
                    steps_payload = result.get("steps")
                    if isinstance(steps_payload, Sequence):
                        planner_span.set_attribute("agent.steps", len(steps_payload))
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
        candidates = _collect_candidates_from_steps(
            steps if isinstance(steps, Sequence) else None
        )
        if candidates:
            response.setdefault("candidates", candidates)
            response.setdefault("results", candidates)

        summaries = _summarize_tool_steps(steps if isinstance(steps, Sequence) else None)
        if summaries and current_app.logger.isEnabledFor(10):  # DEBUG
            current_app.logger.debug(
                "planner tool summary query='%s': %s", query, "; ".join(summaries)
            )
        if turn_span is not None and isinstance(steps, Sequence):
            turn_span.set_attribute("agent.steps", len(steps))
        if turn_span is not None and used_model:
            turn_span.set_attribute("agent.llm_model", used_model)

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
    seeds_raw = payload.get("seeds")
    if isinstance(seeds_raw, Sequence):
        seeds: list[str] = []
        for entry in seeds_raw:
            if isinstance(entry, str) and entry.strip():
                seeds.append(entry.strip())
        if not seeds:
            return jsonify({"ok": False, "error": "seeds_required"}), 400
        mode = payload.get("mode", "fresh")
        if mode not in {"fresh", "incremental"}:
            return jsonify({"ok": False, "error": "invalid_mode"}), 400
        job_id = create_crawl_job(seeds, mode)
        return jsonify({"ok": True, "data": {"job_id": job_id}}), 202
    inputs = {"url": payload.get("url"), "depth": payload.get("depth")}
    with start_span(
        "http.crawl.validate",
        attributes={
            "http.route": "/api/crawl",
            "http.method": request.method,
        },
        inputs=inputs,
    ):
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
    raw_args = {
        "query": request.args.get("q"),
        "llm": request.args.get("llm"),
        "model": request.args.get("model"),
        "page": request.args.get("page"),
        "size": request.args.get("size"),
        "shipit": request.args.get("shipit"),
    }
    try:
        params = SearchQueryParams.model_validate(raw_args)
    except ValidationError as exc:
        return jsonify({"error": "validation_error", "detail": exc.errors()}), 400

    query = params.q
    if params.shipit:
        total, hits, facets = _shipit_search_payload(query, params.page, params.size)
        append_history(
            {
                "id": f"shipit-{hashlib.md5(query.encode('utf-8')).hexdigest()}",
                "query": query,
                "results_count": total,
            }
        )
        payload = {
            "ok": True,
            "data": {
                "total": total,
                "page": params.page,
                "size": params.size,
                "facets": facets,
                "hits": hits,
            },
        }
        return jsonify(payload)

    llm_enabled = params.llm
    llm_model = params.model
    with start_span(
        "http.search",
        attributes={
            "http.route": "/api/search",
            "http.method": request.method,
            "llm.enabled": bool(llm_enabled),
        },
        inputs={"query": query, "model": llm_model},
    ) as span:
        if llm_enabled:
            agent_payload = run_agent(query, model=llm_model)
            if span is not None:
                span.set_attribute("search.mode", "agent")
            return jsonify(agent_payload)

        engine_config: EngineConfig | None = current_app.config.get("RAG_ENGINE_CONFIG")
        store = current_app.config.get("RAG_VECTOR_STORE")
        embedder = current_app.config.get("RAG_EMBEDDER")
        coldstart = current_app.config.get("RAG_COLDSTART")
        rag_agent = current_app.config.get("RAG_AGENT")
        embed_manager: EmbeddingManager | None = current_app.config.get("RAG_EMBED_MANAGER")

        rag_components_ready = all(component is not None for component in (store, embedder, coldstart, rag_agent))

        if engine_config is None or not rag_components_ready:
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
                if span is not None:
                    span.set_attribute("search.results", len(results))
                    if job_id:
                        span.set_attribute("search.focused_job", True)
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
                try:
                    response_payload = SearchResponsePayload.model_validate(payload)
                    return jsonify(response_payload.model_dump(exclude_none=True))
                except ValidationError as exc:
                    current_app.logger.debug("search payload validation failed", exc_info=True)
                    return jsonify(payload)
            return jsonify({"error": "search_service_unavailable"}), 503
        else:
            store = cast(VectorStore, store)
            embedder = cast(OllamaEmbedder, embedder)
            coldstart = cast(ColdStartIndexer, coldstart)
            rag_agent = cast(RagAgent, rag_agent)

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
                payload = _embedding_unavailable_payload(
                    f"{message} ({exc})", status=embed_status
                )
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
