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
    filters = payload.get("filters") if isinstance(payload.get("filters"), Mapping) else None
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


__all__ = ["bp"]
