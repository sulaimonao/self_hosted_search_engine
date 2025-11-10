"""Vector index management API."""

from __future__ import annotations

from typing import Any, Mapping

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


def _run_hybrid_search(
    query: str, *, k: int, filters: Mapping[str, Any] | None
) -> dict[str, Any]:
    filters_dict = dict(filters or {})
    vector_hits = _service().search(query, k=k, filters=filters_dict or None)
    top_score = 0.0
    for hit in vector_hits:
        try:
            score = float(hit.get("score") or 0.0)
        except (TypeError, ValueError):
            score = 0.0
        if score > top_score:
            top_score = score

    keyword_hits: list[dict[str, Any]] = []
    keyword_used = False
    search_service = current_app.config.get("SEARCH_SERVICE")
    if (not vector_hits or top_score < 0.3) and search_service is not None:
        try:
            whoosh_results, _job_id, _context = search_service.run_query(
                query,
                limit=k,
                use_llm=False,
                model=None,
            )
        except Exception:  # pragma: no cover - defensive fallback
            whoosh_results = []
        if whoosh_results:
            keyword_used = True
            for item in whoosh_results:
                keyword_hits.append(
                    {
                        "url": item.get("url"),
                        "title": item.get("title"),
                        "snippet": item.get("snippet"),
                        "score": item.get("score"),
                        "source": "keyword",
                    }
                )

    combined: list[dict[str, Any]] = []
    seen: set[str | None] = set()
    for hit in vector_hits:
        url = hit.get("url")
        seen.add(url)
        combined.append(
            {
                "url": url,
                "title": hit.get("title"),
                "snippet": hit.get("chunk"),
                "score": hit.get("score"),
                "source": "vector",
            }
        )
    for hit in keyword_hits:
        url = hit.get("url")
        if url in seen:
            continue
        seen.add(url)
        combined.append(hit)

    return {
        "query": query,
        "vector": vector_hits,
        "keyword": keyword_hits,
        "combined": combined,
        "filters": filters_dict,
        "vector_top_score": top_score,
        "keyword_fallback": keyword_used,
    }


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
        "status": (status_snapshot.get("state") if isinstance(status_snapshot, Mapping) else None) or "queued",
        "created": created,
        "scope": scope,
        "query": query,
    }
    return jsonify(payload), 202


__all__ = ["bp"]
