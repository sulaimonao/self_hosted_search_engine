"""REST endpoints for managing persisted application configuration."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from .util import get_db
from ..config.models import AppConfig
from ..config.store import read_config, write_config

bp = Blueprint("config", __name__, url_prefix="/api/config")


@bp.get("")
def get_config():
    with get_db() as conn:
        config = read_config(conn)
    return jsonify(config.model_dump())


@bp.put("")
def put_config():
    payload = request.get_json(force=True) or {}
    config = AppConfig(**payload)

    with get_db() as conn:
        write_config(conn, config)

    return jsonify({"ok": True})


@bp.get("/schema")
def get_schema():
    return jsonify(AppConfig.model_json_schema())


__all__ = ["bp", "get_config", "put_config", "get_schema"]
