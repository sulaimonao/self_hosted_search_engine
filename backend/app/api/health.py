"""Health check endpoints for Ollama and other services."""

from __future__ import annotations

from flask import Blueprint, jsonify

from backend.app.llm.ollama_client import OllamaClient, OllamaClientError, DEFAULT_OLLAMA_HOST

bp = Blueprint("health_api", __name__, url_prefix="/api/health")


@bp.get("/ollama")
def ollama_health():
    """Check Ollama connectivity and available models."""
    client = OllamaClient()
    try:
        payload = client.health()
    except OllamaClientError as exc:
        return jsonify({"ok": False, "host": client.base_url, "error": str(exc)}), 503
    except Exception as exc:
        return jsonify({"ok": False, "host": client.base_url, "error": str(exc)}), 503

    return jsonify({"ok": True, "host": client.base_url, "tags": payload})


__all__ = ["bp"]
