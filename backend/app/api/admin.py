"""Minimal admin blueprint used for health checks and pytest imports."""

from __future__ import annotations

from flask import Blueprint, Response, jsonify

from backend.app.llm.ollama_client import OllamaClient, OllamaClientError

bp = Blueprint("admin_api", __name__, url_prefix="/api/admin")


@bp.get("/ping")
def ping() -> tuple[Response, int]:
    """Return a simple success payload used by tests."""

    return jsonify({"ok": True, "service": "admin"}), 200


@bp.get("/ollama/health")
def ollama_health() -> tuple[Response, int]:
    """Check connectivity with the local Ollama instance."""

    client = OllamaClient()
    try:
        payload = client.health()
    except OllamaClientError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 503
    except Exception as exc:  # pragma: no cover - defensive guard for runtime issues
        return jsonify({"ok": False, "error": str(exc)}), 503

    models = []
    for item in payload.get("models", []) if isinstance(payload, dict) else []:
        if isinstance(item, dict):
            name = item.get("name")
            if isinstance(name, str) and name:
                models.append(name)

    return jsonify({"ok": True, "models": models}), 200


__all__ = ["bp", "ping", "ollama_health"]
