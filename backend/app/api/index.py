"""Vector index management API."""

from __future__ import annotations

from typing import Any, Mapping

from flask import Blueprint, current_app, jsonify, request

from backend.app.services.vector_index import (
    EmbedderUnavailableError,
    VectorIndexService,
)


bp = Blueprint("index_api", __name__, url_prefix="/api/index")


def _service() -> VectorIndexService:
    service = current_app.config.get("VECTOR_INDEX_SERVICE")
    if service is None:  # pragma: no cover - configured in app factory
        raise RuntimeError("VECTOR_INDEX_SERVICE not configured")
    return service


def _coerce_str(value: Any) -> str | None:
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return None


def _coerce_metadata(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    return {str(key): item for key, item in value.items()}


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


@bp.post("/search")
def search_index() -> tuple[Any, int]:
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

    vector_hits = _service().search(query, k=k, filters=filters or None)
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

    payload = {
        "query": query,
        "vector": vector_hits,
        "keyword": keyword_hits,
        "combined": combined,
        "filters": filters,
        "vector_top_score": top_score,
        "keyword_fallback": keyword_used,
    }
    return jsonify(payload), 200


__all__ = ["bp"]
