"""Health check endpoints for Ollama and other services."""

from __future__ import annotations

import os
import requests
from flask import Blueprint, jsonify

bp = Blueprint("health_api", __name__, url_prefix="/api/health")

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")


@bp.get("/ollama")
def ollama_health():
    """Check Ollama connectivity and available models."""
    try:
        r = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=5)
        r.raise_for_status()
        tags = r.json()
        return jsonify({"ok": True, "host": OLLAMA_HOST, "tags": tags})
    except Exception as e:
        return jsonify({"ok": False, "host": OLLAMA_HOST, "error": str(e)}), 503


__all__ = ["bp"]
