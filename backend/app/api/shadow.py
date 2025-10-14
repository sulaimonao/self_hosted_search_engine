"""Shadow indexing API endpoints."""

from __future__ import annotations

from typing import Any, Mapping

from flask import Blueprint, current_app, jsonify, request, send_file

from backend.app.config import AppConfig
from backend.app.shadow import ShadowCaptureService, ShadowPolicy, ShadowPolicyStore

bp = Blueprint("shadow_api", __name__, url_prefix="/api/shadow")


def _get_manager():
    return current_app.config.get("SHADOW_INDEX_MANAGER")


def _policy_store() -> ShadowPolicyStore | None:
    store = current_app.config.get("SHADOW_POLICY_STORE")
    if isinstance(store, ShadowPolicyStore):
        return store
    return None


def _capture_service() -> ShadowCaptureService | None:
    service = current_app.config.get("SHADOW_CAPTURE_SERVICE")
    if isinstance(service, ShadowCaptureService):
        return service
    return None


def _manager_or_unavailable():
    manager = _get_manager()
    if manager is None:
        return None, (jsonify({"error": "shadow_unavailable"}), 503)
    return manager, None


def _policy_or_unavailable():
    store = _policy_store()
    if store is None:
        return None, (jsonify({"error": "policy_unavailable"}), 503)
    return store, None


def _capture_or_unavailable():
    service = _capture_service()
    if service is None:
        return None, (jsonify({"error": "capture_unavailable"}), 503)
    return service, None


def _coerce_enabled(value) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "on", "yes"}:
            return True
        if normalized in {"0", "false", "off", "no"}:
            return False
    return None


def _parse_tab_id(value) -> int | None:
    if isinstance(value, (int, float)):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    if isinstance(value, str):
        trimmed = value.strip()
        if trimmed:
            try:
                return int(float(trimmed))
            except (TypeError, ValueError):
                return None
    return None


def _policy_to_payload(policy: ShadowPolicy) -> dict[str, Any]:
    data = policy.to_dict()
    data["ttl_seconds"] = int(policy.ttl_days * 86400)
    return data


def _ensure_enabled_flag(manager, config: dict[str, Any] | None) -> tuple[dict[str, Any], bool]:
    if not isinstance(config, dict):
        config = {}
    enabled_value = config.get("enabled")
    if enabled_value is None:
        getter = getattr(manager, "is_enabled", None)
        if callable(getter):
            try:
                enabled_value = getter()
            except Exception:  # pragma: no cover - defensive guard
                enabled_value = None
        if enabled_value is None and hasattr(manager, "enabled"):
            enabled_value = getattr(manager, "enabled")
    enabled_bool = bool(enabled_value)
    config["enabled"] = enabled_bool
    return config, enabled_bool


@bp.get("")
def shadow_config():
    manager, error_response = _manager_or_unavailable()
    if error_response is not None:
        return error_response

    config, _ = _ensure_enabled_flag(manager, manager.get_config())
    policy_store = _policy_store()
    if policy_store is not None:
        config["policy"] = _policy_to_payload(policy_store.get_global())
        config["policies_updated_at"] = policy_store.snapshot().get("updated_at")
    return jsonify(config), 200


@bp.post("")
def update_shadow_config():
    manager, error_response = _manager_or_unavailable()
    if error_response is not None:
        return error_response

    payload = request.get_json(silent=True) or {}
    enabled_value = _coerce_enabled(payload.get("enabled"))
    if enabled_value is None:
        return jsonify({"error": "invalid_enabled"}), 400

    config, enabled_state = _ensure_enabled_flag(manager, manager.set_enabled(enabled_value))
    config["enabled"] = enabled_state
    policy_store = _policy_store()
    if policy_store is not None:
        policy_store.update_global({"enabled": enabled_state})
        config["policy"] = _policy_to_payload(policy_store.get_global())
    return jsonify(config), 200


@bp.post("/toggle")
def toggle_shadow():
    manager, error_response = _manager_or_unavailable()
    if error_response is not None:
        return error_response
    config, enabled_state = _ensure_enabled_flag(manager, manager.toggle())
    config["enabled"] = enabled_state
    policy_store = _policy_store()
    if policy_store is not None:
        policy_store.update_global({"enabled": enabled_state})
        config["policy"] = _policy_to_payload(policy_store.get_global())
    return jsonify(config), 200


@bp.post("/queue")
def queue_shadow():
    payload = request.get_json(silent=True) or {}
    url = (payload.get("url") or "").strip()
    if not url:
        return jsonify({"error": "url_required"}), 400
    tab_id = _parse_tab_id(payload.get("tabId"))
    reason = payload.get("reason")
    if isinstance(reason, str):
        reason = reason.strip() or None

    manager, error_response = _manager_or_unavailable()
    if error_response is not None:
        return error_response
    try:
        state = manager.enqueue(url, tab_id=tab_id, reason=reason)
    except ValueError:
        return jsonify({"error": "url_required"}), 400
    except RuntimeError as exc:
        if str(exc) == "shadow_disabled":
            return jsonify({"error": "shadow_disabled"}), 409
        raise
    return jsonify(state), 202


@bp.post("/crawl")
def crawl_shadow():
    payload = request.get_json(silent=True) or {}
    url = (payload.get("url") or "").strip()
    if not url:
        return jsonify({"error": "url_required"}), 400
    tab_id = _parse_tab_id(payload.get("tabId"))
    reason = payload.get("reason")
    if isinstance(reason, str):
        reason = reason.strip() or None

    manager, error_response = _manager_or_unavailable()
    if error_response is not None:
        return error_response
    try:
        state = manager.enqueue(url, tab_id=tab_id, reason=reason)
    except ValueError:
        return jsonify({"error": "url_required"}), 400
    except RuntimeError as exc:
        if str(exc) == "shadow_disabled":
            return jsonify({"error": "shadow_disabled"}), 409
        raise
    return jsonify(state), 202


@bp.get("/status")
def shadow_status():
    job_id = (request.args.get("jobId") or "").strip()
    manager, error_response = _manager_or_unavailable()
    if error_response is not None:
        return error_response
    if job_id:
        try:
            status = manager.job_status(job_id)
        except ValueError:
            return jsonify({"error": "job_id_required"}), 400
        if status is None:
            return jsonify({"error": "not_found"}), 404
        return jsonify(status), 200
    url = (request.args.get("url") or "").strip()
    if url:
        status = manager.status_by_url(url)
        return jsonify(status), 200
    return jsonify({"error": "job_id_required"}), 400


@bp.get("/policy")
def get_global_policy():
    store, error_response = _policy_or_unavailable()
    if error_response is not None:
        return error_response
    policy = store.get_global()
    return jsonify({"policy": _policy_to_payload(policy)}), 200


@bp.post("/policy")
def update_global_policy():
    store, error_response = _policy_or_unavailable()
    if error_response is not None:
        return error_response
    payload = request.get_json(silent=True)
    if not isinstance(payload, Mapping):
        return jsonify({"error": "invalid_payload"}), 400
    policy = store.update_global(payload)
    manager = _get_manager()
    if manager is not None:
        manager.set_enabled(bool(policy.enabled))
    return jsonify({"policy": _policy_to_payload(policy)}), 200


@bp.get("/policy/domains")
def list_domain_policies():
    store, error_response = _policy_or_unavailable()
    if error_response is not None:
        return error_response
    policies = {
        domain: _policy_to_payload(policy)
        for domain, policy in store.list_domains().items()
    }
    return jsonify({"policies": policies}), 200


@bp.get("/policy/<path:domain>")
def get_domain_policy(domain: str):
    store, error_response = _policy_or_unavailable()
    if error_response is not None:
        return error_response
    try:
        overrides = store.list_domains()
        policy = overrides.get(domain.strip().lower())
        inherited = False
        if policy is None:
            policy = store.get_domain(domain)
            inherited = True
    except ValueError:
        return jsonify({"error": "invalid_domain"}), 400
    return jsonify({"policy": _policy_to_payload(policy), "inherited": inherited}), 200


@bp.post("/policy/<path:domain>")
def update_domain_policy(domain: str):
    store, error_response = _policy_or_unavailable()
    if error_response is not None:
        return error_response
    payload = request.get_json(silent=True)
    if not isinstance(payload, Mapping):
        return jsonify({"error": "invalid_payload"}), 400
    try:
        policy = store.update_domain(domain, payload)
    except ValueError:
        return jsonify({"error": "invalid_domain"}), 400
    return jsonify({"policy": _policy_to_payload(policy), "inherited": False}), 200


@bp.post("/snapshot")
def snapshot_capture():
    service, error_response = _capture_or_unavailable()
    if error_response is not None:
        return error_response
    payload = request.get_json(silent=True)
    if not isinstance(payload, Mapping):
        return jsonify({"error": "invalid_payload"}), 400
    try:
        result = service.process_snapshot(payload)
    except Exception as exc:  # pragma: no cover - defensive logging
        current_app.logger.exception("shadow.snapshot_error: %s", exc)
        return jsonify({"error": "snapshot_failed"}), 500
    return jsonify(result.payload), result.status


@bp.get("/artifact")
def download_artifact():
    path_param = (request.args.get("path") or "").strip()
    if not path_param:
        return jsonify({"error": "path_required"}), 400
    config = current_app.config.get("APP_CONFIG")
    if not isinstance(config, AppConfig):
        return jsonify({"error": "artifact_unavailable"}), 503
    base = (config.agent_data_dir / "documents").resolve()
    target = (base / path_param).resolve()
    try:
        target.relative_to(base)
    except ValueError:
        return jsonify({"error": "invalid_path"}), 400
    if not target.exists() or not target.is_file():
        return jsonify({"error": "not_found"}), 404
    return send_file(target)


__all__ = ["bp"]
