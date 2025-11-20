"""Vector index management API."""

from __future__ import annotations

import os
import re
from typing import Any, Mapping
from urllib.parse import urlparse

from flask import Blueprint, current_app, jsonify, request

from backend.app.services.vector_index import (
    EmbedderUnavailableError,
    VectorIndexService,
)
from server.refresh_worker import RefreshWorker
from backend.app.shadow.manager import ShadowIndexer


bp = Blueprint("index_api", __name__, url_prefix="/api/index")


def _service() -> VectorIndexService:
    service = current_app.config.get("VECTOR_INDEX_SERVICE")
    if service is None:  # pragma: no cover - configured in app factory
        raise RuntimeError("VECTOR_INDEX_SERVICE not configured")
    return service


def _shadow_manager() -> ShadowIndexer:
    manager = current_app.config.get("SHADOW_INDEX_MANAGER")
    if not isinstance(manager, ShadowIndexer):
        raise RuntimeError("SHADOW_INDEX_MANAGER not configured")
    return manager


def _refresh_worker() -> RefreshWorker:
    worker = current_app.config.get("REFRESH_WORKER")
    if not isinstance(worker, RefreshWorker):
        raise RuntimeError("REFRESH_WORKER not configured")
    return worker


_SCOPE_DEFAULTS: dict[str, dict[str, int]] = {
    "page": {"budget": 1, "depth": 1},
    "domain": {"budget": 40, "depth": 3},
    "site": {"budget": 80, "depth": 4},
}


def _coerce_str(value: Any) -> str | None:
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return None


def _coerce_metadata(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    return {str(key): item for key, item in value.items()}


def _tokenize_query(query: str) -> list[str]:
    terms = re.findall(r"[a-z0-9]+", (query or "").lower())
    return [term for term in terms if term]


def _highlight_terms(text: str, terms: list[str], *, limit: int = 360) -> str:
    cleaned = (text or "").strip()
    if not cleaned or not terms:
        return cleaned[:limit]
    pattern = re.compile(r"(" + "|".join(re.escape(term) for term in terms) + r")", re.IGNORECASE)

    def _mark(match: re.Match[str]) -> str:
        return f"<mark>{match.group(0)}</mark>"

    highlighted = pattern.sub(_mark, cleaned)
    if len(highlighted) <= limit:
        return highlighted
    return highlighted[:limit] + "…"


def _domain_from_url(url: str | None) -> str | None:
    if not url:
        return None
    try:
        parsed = urlparse(url)
    except Exception:
        return None
    if parsed.hostname:
        return parsed.hostname
    return None


def _normalize_weights(keyword_weight: float, vector_weight: float) -> tuple[float, float]:
    kw = max(0.0, float(keyword_weight))
    vec = max(0.0, float(vector_weight))
    total = kw + vec
    if total <= 0:
        return 0.5, 0.5
    return kw / total, vec / total


HYBRID_BM25_WEIGHT = float(os.getenv("HYBRID_KEYWORD_WEIGHT", "0.6"))
HYBRID_VECTOR_WEIGHT = float(os.getenv("HYBRID_VECTOR_WEIGHT", "0.4"))
HYBRID_MAX_CANDIDATES = max(10, int(os.getenv("HYBRID_CANDIDATE_POOL", "40")))


def _run_hybrid_search(
    query: str, *, k: int, filters: Mapping[str, Any] | None
) -> dict[str, Any]:
    filters_dict = dict(filters or {})
    keyword_weight, vector_weight = _normalize_weights(
        HYBRID_BM25_WEIGHT, HYBRID_VECTOR_WEIGHT
    )
    search_service = current_app.config.get("SEARCH_SERVICE")
    keyword_hits: list[dict[str, Any]] = []
    job_id = None
    context: dict[str, Any] = {}
    candidate_limit = min(max(k * 2, k + 5), HYBRID_MAX_CANDIDATES)
    if search_service is not None:
        try:
            keyword_hits, job_id, context = search_service.run_query(
                query,
                limit=candidate_limit,
                use_llm=False,
                model=None,
            )
        except Exception:  # pragma: no cover - defensive fallback
            keyword_hits = []
            context = {}
            job_id = None

    terms = _tokenize_query(query)
    vector_hits: list[dict[str, Any]] = []
    embed_error: dict[str, Any] | None = None
    try:
        vector_hits = _service().search(
            query, k=candidate_limit, filters=filters_dict or None
        )
    except EmbedderUnavailableError as exc:
        embed_error = {
            "error": "embedding_unavailable",
            "detail": exc.detail,
            "model": exc.model,
            "autopull_started": exc.autopull_started,
        }
        vector_hits = []

    candidates: dict[str, dict[str, Any]] = {}
    keyword_top_score = 0.0
    for item in keyword_hits:
        url = item.get("url")
        if not url:
            continue
        bm25_score = float(item.get("blended_score") or item.get("score") or 0.0)
        keyword_top_score = max(keyword_top_score, bm25_score)
        entry = candidates.setdefault(
            url,
            {
                "url": url,
                "title": item.get("title") or url,
                "snippet": item.get("snippet") or "",
                "lang": item.get("lang"),
            },
        )
        entry["keyword_score"] = bm25_score
        entry["source"] = "keyword"
        entry["match_reason"] = "keyword"
        entry["domain"] = _domain_from_url(url)

    vector_top_score = 0.0
    for item in vector_hits:
        url = item.get("url")
        if not url:
            continue
        vector_score = float(item.get("score") or 0.0)
        vector_top_score = max(vector_top_score, vector_score)
        snippet = _highlight_terms(item.get("chunk") or "", terms)
        entry = candidates.setdefault(
            url,
            {
                "url": url,
                "title": item.get("title") or url,
                "snippet": snippet,
                "lang": item.get("lang"),
            },
        )
        entry["vector_score"] = vector_score
        entry["vector_snippet"] = snippet
        entry["source"] = "semantic" if "keyword_score" in entry else "vector"
        entry["domain"] = entry.get("domain") or _domain_from_url(url)
        metadata = (
            item.get("metadata") if isinstance(item, Mapping) else None
        )
        if isinstance(metadata, Mapping):
            entry["metadata"] = dict(metadata)
            if metadata.get("domain") and not entry.get("domain"):
                entry["domain"] = str(metadata.get("domain"))
            if "temp" in metadata:
                entry["temp"] = bool(metadata.get("temp"))
            if metadata.get("source"):
                entry["source"] = str(metadata.get("source"))

    combined: list[dict[str, Any]] = []
    for url, entry in candidates.items():
        kw_score = float(entry.get("keyword_score") or 0.0)
        vec_score = float(entry.get("vector_score") or 0.0)
        norm_kw = kw_score / keyword_top_score if keyword_top_score > 0 else 0.0
        norm_vec = vec_score / vector_top_score if vector_top_score > 0 else 0.0
        blended = (keyword_weight * norm_kw) + (vector_weight * norm_vec)
        if kw_score > 0 and vec_score > 0:
            match_reason = "keyword+semantic"
        elif vec_score > 0:
            match_reason = "semantic"
        else:
            match_reason = "keyword"
        snippet = entry.get("snippet") or entry.get("vector_snippet") or ""
        about_payload = {
            "match_reason": match_reason,
            "keyword_score": kw_score,
            "vector_score": vec_score,
            "normalized_keyword": norm_kw,
            "normalized_vector": norm_vec,
            "weights": {"keyword": keyword_weight, "vector": vector_weight},
        }
        combined.append(
            {
                "id": url,
                "url": url,
                "title": entry.get("title") or url,
                "snippet": snippet,
                "score": kw_score or vec_score,
                "blended_score": blended,
                "match_reason": match_reason,
                "vector_score": vec_score,
                "keyword_score": kw_score,
                "source": entry.get("source"),
                "lang": entry.get("lang"),
                "domain": entry.get("domain"),
                "temp": bool(entry.get("temp", False)),
                "metadata": entry.get("metadata"),
                "about": about_payload,
            }
        )

    combined.sort(key=lambda item: item.get("blended_score", 0.0), reverse=True)
    combined = combined[:k]

    status = "ok"
    detail = None
    if embed_error:
        status = "warming"
        detail = embed_error.get("detail") or "Embedding model unavailable"

    payload = {
        "status": status,
        "detail": detail,
        "query": query,
        "vector": vector_hits,
        "keyword": keyword_hits,
        "combined": combined,
        "hits": combined,
        "filters": filters_dict,
        "vector_top_score": vector_top_score,
        "keyword_top_score": keyword_top_score,
        "keyword_fallback": bool(embed_error),
        "weights": {"keyword": keyword_weight, "vector": vector_weight},
        "job_id": job_id,
        "confidence": context.get("confidence"),
        "trigger_reason": context.get("trigger_reason"),
        "seed_count": context.get("seed_count"),
    }
    if embed_error:
        payload["embedder_status"] = _service().embedding_status()
        payload["code"] = "embedding_unavailable"
    return payload


@bp.post("/upsert")
def upsert_document() -> tuple[Any, int]:
    payload = request.get_json(silent=True) or {}
    text_raw = payload.get("text")
    text_value = str(text_raw) if isinstance(text_raw, str) else None
    if not text_value or not text_value.strip():
        return jsonify({"error": "text is required"}), 400
    url_value = _coerce_str(payload.get("url"))
    title_value = _coerce_str(payload.get("title"))
    metadata = _coerce_metadata(payload.get("meta"))
    try:
        result = _service().upsert_document(
            text=text_value,
            url=url_value,
            title=title_value,
            metadata=metadata,
        )
    except EmbedderUnavailableError as exc:
        response = {
            "error": "embedding_unavailable",
            "detail": exc.detail,
            "model": exc.model,
        }
        if exc.autopull_started:
            response["autopull_started"] = True
        return jsonify(response), 503
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(result.to_dict()), 200


@bp.route("/search", methods=["POST", "OPTIONS"])
def search_index() -> tuple[Any, int]:
    if request.method == "OPTIONS":
        return ("", 204)
    payload = request.get_json(silent=True) or {}
    query = _coerce_str(payload.get("query"))
    if not query:
        return jsonify({"error": "query is required"}), 400
    k_value = payload.get("k", 5)
    try:
        k = max(1, int(k_value))
    except (TypeError, ValueError):
        return jsonify({"error": "k must be an integer"}), 400
    filters = (
        payload.get("filters") if isinstance(payload.get("filters"), Mapping) else None
    )
    try:
        results = _service().search(query, k=k, filters=filters)
    except EmbedderUnavailableError as exc:
        response = {
            "error": "embedding_unavailable",
            "detail": exc.detail,
            "model": exc.model,
        }
        if exc.autopull_started:
            response["autopull_started"] = True
        return jsonify(response), 503
    return jsonify({"results": results}), 200


@bp.get("/search")
def hybrid_search() -> tuple[Any, int]:
    query = _coerce_str(request.args.get("q") or request.args.get("query"))
    if not query:
        return jsonify({"error": "query is required"}), 400

    try:
        k = max(1, int(request.args.get("k", 10)))
    except (TypeError, ValueError):
        return jsonify({"error": "k must be an integer"}), 400

    filters: dict[str, Any] = {}
    domain = _coerce_str(request.args.get("domain"))
    if domain:
        filters["domain"] = domain
    policy_id = _coerce_str(
        request.args.get("policy_id") or request.args.get("policyId")
    )
    if policy_id:
        filters["policy_id"] = policy_id
    hash_filter = _coerce_str(request.args.get("hash"))
    if hash_filter:
        filters["hash"] = hash_filter

    try:
        payload = _run_hybrid_search(query, k=k, filters=filters)
    except EmbedderUnavailableError as exc:
        response = {
            "error": "embedding_unavailable",
            "detail": exc.detail,
            "model": exc.model,
        }
        if exc.autopull_started:
            response["autopull_started"] = True
        return jsonify(response), 503
    return jsonify(payload), 200


@bp.route("/hybrid_search", methods=["POST", "OPTIONS"])
def hybrid_search_post() -> tuple[Any, int]:
    if request.method == "OPTIONS":
        return ("", 204)
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, Mapping):
        return jsonify({"error": "invalid_payload"}), 400

    query = _coerce_str(payload.get("query"))
    if not query:
        return jsonify({"error": "query is required"}), 400

    k_candidate = payload.get("k", payload.get("limit", 10))
    try:
        k = max(1, int(k_candidate))
    except (TypeError, ValueError):
        return jsonify({"error": "k must be an integer"}), 400

    filters: dict[str, Any] = {}
    raw_filters = payload.get("filters")
    if isinstance(raw_filters, Mapping):
        filters.update({str(key): value for key, value in raw_filters.items()})

    domain = _coerce_str(payload.get("domain"))
    if domain:
        filters["domain"] = domain

    policy_id = _coerce_str(payload.get("policy_id") or payload.get("policyId"))
    if policy_id:
        filters["policy_id"] = policy_id

    hash_filter = _coerce_str(payload.get("hash"))
    if hash_filter:
        filters["hash"] = hash_filter

    try:
        payload = _run_hybrid_search(query, k=k, filters=filters)
    except EmbedderUnavailableError as exc:
        response = {
            "error": "embedding_unavailable",
            "detail": exc.detail,
            "model": exc.model,
        }
        if exc.autopull_started:
            response["autopull_started"] = True
        return jsonify(response), 503
    return jsonify(payload), 200


@bp.post("/snapshot")
def snapshot_index() -> tuple[Any, int]:
    payload = request.get_json(silent=True) or {}
    url = _coerce_str(payload.get("url"))
    if not url:
        return jsonify({"error": "url_required"}), 400
    try:
        manager = _shadow_manager()
    except RuntimeError:
        return jsonify({"error": "shadow_unavailable"}), 503
    try:
        snapshot = manager.enqueue(url, reason="chat_index")
    except RuntimeError as exc:
        return jsonify({"error": "shadow_disabled", "message": str(exc)}), 503
    except ValueError as exc:
        return jsonify({"error": "invalid_url", "message": str(exc)}), 400
    response = {
        "jobId": snapshot.get("jobId") or snapshot.get("job_id"),
        "status": snapshot.get("state") or "queued",
        "phase": snapshot.get("phase"),
        "url": snapshot.get("url") or url,
        "message": snapshot.get("message") or "Queued for shadow indexing",
    }
    return jsonify(response), 202


@bp.post("/site")
def index_site() -> tuple[Any, int]:
    payload = request.get_json(silent=True) or {}
    url = _coerce_str(payload.get("url"))
    if not url:
        return jsonify({"error": "url_required"}), 400
    scope = _coerce_str(payload.get("scope")) or "domain"
    defaults = _SCOPE_DEFAULTS.get(scope, _SCOPE_DEFAULTS["domain"])
    try:
        worker = _refresh_worker()
    except RuntimeError:
        return jsonify({"error": "refresh_unavailable"}), 503
    query = f"index:{url}"
    try:
        job_id, status_snapshot, created = worker.enqueue(
            query,
            use_llm=False,
            seeds=[url],
            budget=defaults["budget"],
            depth=defaults["depth"],
            force=True,
        )
    except ValueError as exc:
        return jsonify({"error": "invalid_request", "message": str(exc)}), 400

    payload = {
        "jobId": job_id,
        "status": (
            status_snapshot.get("state")
            if isinstance(status_snapshot, Mapping)
            else None
        )
        or "queued",
        "created": created,
        "scope": scope,
        "query": query,
    }
    return jsonify(payload), 202


__all__ = ["bp"]
