"""Agent browser control endpoints (feature gated)."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from ..services.agent_browser import AgentBrowserManager, BrowserActionError, SessionNotFoundError

bp = Blueprint("agent_browser", __name__, url_prefix="/api/agent")


def _manager() -> AgentBrowserManager:
    if not current_app.config.get("AGENT_BROWSER_ENABLED", False):
        raise RuntimeError("Agent browser manager unavailable")

    manager: AgentBrowserManager | None = current_app.config.get("AGENT_BROWSER_MANAGER")
    if manager is None:
        timeout_value = current_app.config.get("AGENT_BROWSER_DEFAULT_TIMEOUT_S", 15)
        try:
            timeout_s = int(timeout_value)
        except (TypeError, ValueError):
            timeout_s = 15

        headless_value = current_app.config.get("AGENT_BROWSER_HEADLESS", True)
        if isinstance(headless_value, str):
            headless_flag = headless_value.lower() in {"1", "true", "yes", "on"}
        else:
            headless_flag = bool(headless_value)

        manager = AgentBrowserManager(
            default_timeout_s=timeout_s,
            headless=headless_flag,
        )
        current_app.config["AGENT_BROWSER_MANAGER"] = manager
    return manager


@bp.get("/health")
def health() -> tuple[str, int]:
    try:
        manager = _manager()
    except RuntimeError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 503

    healthy = manager.health()
    return jsonify({"ok": healthy}), (200 if healthy else 500)


def _handle_action(func):
    try:
        result = func()
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except SessionNotFoundError as exc:
        return jsonify({"error": "unknown_session", "message": str(exc)}), 404
    except BrowserActionError as exc:
        return jsonify({"error": "browser_action_failed", "message": str(exc)}), 502
    return jsonify(result), 200


@bp.post("/session/start")
def start_session() -> tuple[str, int]:
    manager = _manager()
    sid = manager.start_session()
    return jsonify({"sid": sid}), 200


@bp.post("/navigate")
def navigate() -> tuple[str, int]:
    manager = _manager()
    payload = request.get_json(silent=True) or {}
    sid = (payload.get("sid") or "").strip()
    url = (payload.get("url") or "").strip()

    def _action():
        if not sid:
            raise ValueError("sid is required")
        if not url:
            raise ValueError("url is required")
        result = manager.navigate(sid, url)
        result["sid"] = sid
        return result

    return _handle_action(_action)


@bp.post("/click")
def click() -> tuple[str, int]:
    manager = _manager()
    payload = request.get_json(silent=True) or {}
    sid = (payload.get("sid") or "").strip()
    selector = (payload.get("selector") or "").strip()
    text = (payload.get("text") or "").strip()

    def _action():
        if not sid:
            raise ValueError("sid is required")
        if not selector and not text:
            raise ValueError("selector or text is required")
        result = manager.click(sid, selector or None, text or None)
        result["sid"] = sid
        if selector:
            result["selector"] = selector
        if text:
            result["text"] = text
        return result

    return _handle_action(_action)


@bp.post("/type")
def type_into() -> tuple[str, int]:
    manager = _manager()
    payload = request.get_json(silent=True) or {}
    sid = (payload.get("sid") or "").strip()
    selector = (payload.get("selector") or "").strip()
    text = payload.get("text", "")
    if not isinstance(text, str):
        text = str(text)

    def _action():
        if not sid:
            raise ValueError("sid is required")
        if not selector:
            raise ValueError("selector is required")
        result = manager.type(sid, selector, text)
        result["sid"] = sid
        result["selector"] = selector
        return result

    return _handle_action(_action)


@bp.post("/reload")
def reload() -> tuple[str, int]:
    manager = _manager()
    payload = request.get_json(silent=True) or {}
    sid = (payload.get("sid") or "").strip()

    def _action():
        if not sid:
            raise ValueError("sid is required")
        result = manager.reload(sid)
        result["sid"] = sid
        return result

    return _handle_action(_action)


@bp.post("/session/close")
def close_session() -> tuple[str, int]:
    manager = _manager()
    payload = request.get_json(silent=True) or {}
    sid = (payload.get("sid") or "").strip()

    def _action():
        if not sid:
            raise ValueError("sid is required")
        manager.close_session(sid)
        return {"sid": sid, "closed": True}

    return _handle_action(_action)


@bp.post("/extract")
def extract() -> tuple[str, int]:
    manager = _manager()
    payload = request.get_json(silent=True) or {}
    sid = (payload.get("sid") or "").strip()

    def _action():
        if not sid:
            raise ValueError("sid is required")
        result = manager.extract(sid)
        result["sid"] = sid
        return result

    return _handle_action(_action)
