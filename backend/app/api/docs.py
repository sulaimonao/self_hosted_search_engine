"""Document metadata APIs backed by the application state database."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from backend.app.db import AppStateDB

bp = Blueprint("docs_api", __name__, url_prefix="/api")


@bp.get("/docs")
def list_docs():
    query = request.args.get("query", "").strip() or None
    facet = request.args.get("facet", "").strip() or None
    state_db: AppStateDB = current_app.config["APP_STATE_DB"]
    docs = state_db.list_documents(query=query, site=facet, limit=100)
    items = [
        {
            "id": doc.id,
            "url": doc.url,
            "canonical_url": doc.canonical_url,
            "site": doc.site,
            "title": doc.title,
            "language": doc.language,
            "categories": doc.categories,
            "labels": doc.labels,
            "source": doc.source,
            "tokens": doc.tokens,
            "normalized_path": doc.normalized_path,
            "fetched_at": doc.fetched_at,
        }
        for doc in docs
    ]
    return jsonify({"items": items})


@bp.get("/docs/<doc_id>")
def document_detail(doc_id: str):
    state_db: AppStateDB = current_app.config["APP_STATE_DB"]
    doc = state_db.get_document(doc_id)
    if not doc:
        return jsonify({"error": "not_found"}), 404
    return jsonify({"item": doc})


__all__ = ["bp", "list_docs", "document_detail"]
