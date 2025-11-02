"""REST API for reading and updating runtime configuration."""

from __future__ import annotations

from flask import Blueprint, Response, current_app, jsonify, request

from backend.app.services.runtime_config import RuntimeConfigService

bp = Blueprint("config_api", __name__, url_prefix="/api/config")


def _service() -> RuntimeConfigService:
    service = current_app.config.get("RUNTIME_CONFIG_SERVICE")
    if isinstance(service, RuntimeConfigService):
        return service
    raise RuntimeError("Runtime configuration service is not available")


@bp.get("")
def read_config() -> tuple[Response, int]:
    service = _service()
    payload = service.snapshot()
    return jsonify({"config": payload, "schema_version": service.schema_version}), 200


@bp.put("")
def update_config() -> tuple[Response, int]:
    service = _service()
    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify({"error": "JSON body required"}), 400
    if not isinstance(payload, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400
    updated = service.update(payload)
    return jsonify({"config": updated, "schema_version": service.schema_version}), 200


@bp.get("/schema")
def schema() -> tuple[Response, int]:
    service = _service()
    return jsonify(service.schema()), 200


__all__ = ["bp", "read_config", "update_config", "schema"]
