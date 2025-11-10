"""Embedding helpers for manual ingestion requests."""

from __future__ import annotations

from typing import Sequence

from flask import Blueprint, current_app, jsonify, request

from backend.app.services.vector_index import EmbedderUnavailableError, VectorIndexService

bp = Blueprint("embeddings_api", __name__, url_prefix="/api/embeddings")

_MAX_TEXT_INPUT = 20
_MAX_TEXT_LENGTH = 50_000


def _clean_texts(texts: Sequence[object]) -> list[str]:
    cleaned: list[str] = []
    for entry in texts:
        if not isinstance(entry, str):
            continue
        candidate = entry.strip()
        if not candidate:
            continue
        if len(candidate) > _MAX_TEXT_LENGTH:
            candidate = candidate[:_MAX_TEXT_LENGTH]
        cleaned.append(candidate)
        if len(cleaned) >= _MAX_TEXT_INPUT:
            break
    return cleaned


@bp.post("/build")
def build_embeddings():
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"error": "invalid_payload"}), 400
    raw_texts = payload.get("text") or payload.get("texts")
    if isinstance(raw_texts, str):
        texts = [raw_texts]
    elif isinstance(raw_texts, Sequence):
        texts = list(raw_texts)
    else:
        return jsonify({"error": "text_required"}), 400

    cleaned = _clean_texts(texts)
    if not cleaned:
        return jsonify({"error": "text_required"}), 400

    namespace = str(payload.get("namespace") or "chat").strip() or "chat"
    service = current_app.config.get("VECTOR_INDEX_SERVICE")
    if not isinstance(service, VectorIndexService):
        return jsonify({"error": "embedding_unavailable"}), 503

    doc_ids: list[str] = []
    for index, text in enumerate(cleaned, start=1):
        doc_url = f"context://{namespace}/{index}"
        title = f"{namespace} snippet {index}"
        metadata = {"namespace": namespace, "source": "embeddings_api"}
        try:
            result = service.upsert_document(text=text, url=doc_url, title=title, metadata=metadata)
        except EmbedderUnavailableError as exc:
            return (
                jsonify({
                    "error": "embedding_unavailable",
                    "detail": exc.detail,
                    "model": exc.model,
                    "autopull_started": exc.autopull_started,
                }),
                503,
            )
        except ValueError as exc:
            return jsonify({"error": "invalid_text", "message": str(exc)}), 400
        doc_ids.append(result.doc_id)

    return jsonify({"count": len(doc_ids), "namespace": namespace, "docIds": doc_ids})


__all__ = ["bp", "build_embeddings"]
