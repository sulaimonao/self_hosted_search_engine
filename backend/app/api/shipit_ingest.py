"""Ship-It ingest endpoints."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from flask import Blueprint, jsonify, request

bp = Blueprint("shipit_ingest", __name__, url_prefix="/api/ingest")


@bp.post("/webpage")
def ingest_webpage() -> Any:
    payload = request.get_json(silent=True) or {}
    url = payload.get("url")
    if not isinstance(url, str) or not url.strip():
        return jsonify({"ok": False, "error": "url_required"}), 400

    html = payload.get("html")
    snapshot = payload.get("snapshot")
    indexed = bool(html or snapshot)
    doc_id = uuid4().hex
    response = {"ok": True, "data": {"doc_id": doc_id, "indexed": indexed}}
    return jsonify(response), 201


__all__ = ["bp", "ingest_webpage"]
