"""Minimal admin blueprint used for health checks and pytest imports."""

from __future__ import annotations

from flask import Blueprint, Response, current_app, jsonify, request

from backend.app.llm.ollama_client import OllamaClient, OllamaClientError
from backend.app.services import ollama_client

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


@bp.post("/install_models")
def install_models() -> tuple[Response, int]:
    config = current_app.config.get("APP_CONFIG")
    if config is None:
        return jsonify({"ok": False, "error": "config_unavailable"}), 503
    if not getattr(config, "dev_allow_autopull", False):
        return jsonify({"ok": False, "error": "autopull_disabled"}), 403

    payload = request.get_json(silent=True) or {}
    models_raw = payload.get("models")
    if not isinstance(models_raw, (list, tuple)) or not models_raw:
        return jsonify({"ok": False, "error": "models_required"}), 400

    engine_config = current_app.config.get("RAG_ENGINE_CONFIG")
    base_url = getattr(getattr(engine_config, "ollama", None), "base_url", None)

    started: list[dict[str, object]] = []
    missing_cli = False
    for entry in models_raw:
        candidate = entry if isinstance(entry, str) else None
        if not candidate:
            continue
        name = ollama_client.resolve_model_name(
            candidate, base_url=base_url, chat_only=False
        )
        try:
            process = ollama_client.pull_model(name, base_url=base_url)
        except FileNotFoundError:
            missing_cli = True
            break
        except Exception as exc:  # pragma: no cover - subprocess edge cases
            started.append({"model": name, "ok": False, "error": str(exc)})
        else:
            started.append({"model": name, "ok": True, "pid": process.pid})

    if missing_cli:
        return jsonify({"ok": False, "error": "ollama_cli_missing"}), 503

    if not started:
        return jsonify({"ok": False, "error": "no_valid_models"}), 400

    return jsonify({"ok": True, "results": started}), 202


__all__ = ["bp", "ping", "ollama_health", "install_models"]
