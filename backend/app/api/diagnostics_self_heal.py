"""Diagnostics-scoped aliases and utilities for self-heal planner and executor."""
from __future__ import annotations

import difflib
import logging
from typing import Any, Dict

from flask import Blueprint, jsonify, request
from werkzeug.exceptions import HTTPException

from backend.app.api import self_heal as self_heal_module
from backend.app.api.self_heal_execute import execute_headless as _headless
from backend.app.self_heal.episodes import get_episode_by_id, iter_episodes
from backend.app.self_heal.metrics import metrics_snapshot
from backend.app.self_heal.rules import (
    add_rule,
    apply_order,
    enable_rule,
    load_rulepack,
    propose_rule_from_episode,
    read_rulepack_text,
)

bp = Blueprint("diagnostics_self_heal_api", __name__, url_prefix="/api/diagnostics")

LOGGER = logging.getLogger(__name__)
_FALLBACK_DIRECTIVE = {"reason": "fallback: reload", "steps": [{"type": "reload"}]}


@bp.post("/self_heal")
def diagnostics_self_heal():
    """Proxy planner requests through the diagnostics namespace."""

    try:
        return self_heal_module.self_heal()
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive fallback
        LOGGER.exception("diagnostics self-heal proxy failed; returning fallback reload directive")
        emit = getattr(self_heal_module, "_emit", None)
        if callable(emit):
            try:
                emit(
                    "planner.fallback",
                    "Diagnostics proxy returned fallback reload directive.",
                    error=str(exc),
                )
            except Exception:  # pragma: no cover - telemetry best effort
                LOGGER.debug("diagnostics fallback emit failed", exc_info=True)
        timeout_value = getattr(self_heal_module, "_PLAN_TIMEOUT_S", None)
        payload: Dict[str, Any] = {
            "mode": "plan",
            "directive": _FALLBACK_DIRECTIVE,
            "meta": {
                "source": "diagnostics_proxy",
                "planner_status": "proxy_error",
                "error": str(exc),
            },
            "took_ms": 0,
        }
        if timeout_value is not None:
            payload["meta"]["planner_timeout_s"] = float(timeout_value)
        return jsonify(payload), 200


@bp.post("/self_heal/execute_headless")
def diagnostics_self_heal_execute():
    """Proxy headless execution through the diagnostics namespace."""

    return _headless()


@bp.get("/rules")
def diagnostics_rulepack_summary():
    rules = load_rulepack()
    yaml_text = read_rulepack_text()
    return jsonify({
        "rules": rules,
        "yaml": yaml_text,
        "metrics": metrics_snapshot(),
    })


@bp.get("/rules/episodes")
def diagnostics_rulepack_episodes():
    limit_raw = request.args.get("limit", "100")
    try:
        limit = max(1, min(500, int(limit_raw)))
    except ValueError:
        limit = 100
    episodes = list(iter_episodes(limit=limit))
    return jsonify({"episodes": episodes})


@bp.post("/rules/update")
def diagnostics_rulepack_update():
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"error": "invalid_payload"}), 400
    rules: list[Dict[str, Any]]
    if "order" in payload and isinstance(payload.get("order"), list):
        order = [str(item) for item in payload["order"]]
        rules = apply_order(order)
    elif "rule_id" in payload and "enabled" in payload:
        rule_id = str(payload.get("rule_id") or "")
        enabled = bool(payload.get("enabled"))
        rules = enable_rule(rule_id, enabled)
    else:
        return jsonify({"error": "unsupported_operation"}), 400
    return jsonify({
        "rules": rules,
        "yaml": read_rulepack_text(),
        "metrics": metrics_snapshot(),
    })


@bp.post("/rules/promote")
def diagnostics_rulepack_promote():
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"error": "invalid_payload"}), 400

    episode: Dict[str, Any] | None = None
    episode_id = payload.get("episode_id")
    if isinstance(episode_id, str) and episode_id:
        episode = get_episode_by_id(episode_id)
        if episode is None:
            return jsonify({"error": "episode_not_found"}), 404
    elif isinstance(payload.get("episode"), dict):
        episode = payload["episode"]  # type: ignore[assignment]
    if episode is None:
        return jsonify({"error": "episode_required"}), 400

    rule = propose_rule_from_episode(episode, default_enabled=False)
    before = read_rulepack_text()
    try:
        rule_id, rules = add_rule(rule)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    after = read_rulepack_text()
    diff = "\n".join(
        difflib.unified_diff(
            before.splitlines(),
            after.splitlines(),
            fromfile="rulepack.yml (before)",
            tofile="rulepack.yml (after)",
            lineterm="",
        )
    )
    return jsonify({
        "rule_id": rule_id,
        "rule": rule,
        "yaml_diff": diff,
        "rules": rules,
        "enabled": False,
        "yaml": after,
        "metrics": metrics_snapshot(),
    })


__all__ = ["bp"]
