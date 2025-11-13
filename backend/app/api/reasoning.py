"""Reasoning helpers coordinating LLM prompts with optional browser routing."""

from __future__ import annotations

from typing import Any

from flask import Blueprint, current_app, jsonify, request

from backend.app.services import ollama_client

from .web_search import web_search

bp = Blueprint("reasoning_api", __name__, url_prefix="/api")


def _configured_model(default: str = "gpt-oss") -> str:
    config = current_app.config.get("RAG_ENGINE_CONFIG")
    if config is None:
        return default
    primary = getattr(getattr(config, "models", None), "llm_primary", None)
    if isinstance(primary, str) and primary.strip():
        return primary.strip()
    return default


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return False


def route_to_browser(
    query: str,
    *,
    reason: str | None = None,
    limit: int = 5,
    model: str | None = None,
) -> dict[str, Any]:
    """Build an autopilot directive instructing the UI to open the browser."""

    trimmed = (query or "").strip()
    reason_text = (reason or "").strip() or "User requested browser assistance."
    results = web_search(trimmed, limit=limit, use_llm=False, model=model)
    top_url = next((item.get("url") for item in results if item.get("url")), trimmed)
    top_title = next(
        (item.get("title") for item in results if item.get("title")), "Result"
    )

    tool_payload = {
        "label": "Open top result",
        "endpoint": "/api/browser/history",
        "method": "POST",
        "payload": {
            "url": top_url,
            "title": top_title,
            "source": "reasoning-route",
        },
        "description": "Record the top search result in history for quick access.",
    }

    directive: dict[str, Any] = {
        "mode": "browser",
        "query": trimmed,
        "reason": reason_text,
        "tools": [tool_payload],
    }
    return directive


@bp.post("/reasoning")
def reasoning_endpoint():
    payload = request.get_json(silent=True) or {}
    query = str(payload.get("query") or "").strip()
    if not query:
        return jsonify({"error": "query_required"}), 400

    requested_model = str(payload.get("model") or "").strip() or None
    resolved_model = requested_model or _configured_model()
    resolved_model = ollama_client.resolve_model_name(resolved_model, chat_only=True)
    use_browser = _coerce_bool(payload.get("use_browser"))
    browser_reason = (
        str(payload.get("browser_reason") or payload.get("reason") or "").strip()
        or None
    )
    limit = payload.get("limit")
    try:
        limit_value = int(limit) if limit not in (None, "") else 5
    except (TypeError, ValueError):
        limit_value = 5
    limit_value = max(1, min(limit_value, 10))

    response: dict[str, Any] = {
        "query": query,
        "model": resolved_model,
        "use_browser": use_browser,
    }

    if use_browser:
        response["browser"] = {
            "results": web_search(
                query, limit=limit_value, use_llm=False, model=resolved_model
            )
        }
        response["autopilot"] = route_to_browser(
            query,
            reason=browser_reason,
            limit=limit_value,
            model=resolved_model,
        )

    return jsonify(response)


__all__ = ["bp", "route_to_browser"]
