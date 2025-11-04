"""Low-level helpers for reading and writing application configuration."""

from __future__ import annotations

import json
from sqlite3 import Connection
from typing import Any

from .models import AppConfig

_DB_TO_MODEL = {
    "models.primary": "models_primary",
    "models.fallback": "models_fallback",
    "models.embedder": "models_embedder",
    "features.shadow_mode": "features_shadow_mode",
    "features.agent_mode": "features_agent_mode",
    "features.local_discovery": "features_local_discovery",
    "features.browsing_fallbacks": "features_browsing_fallbacks",
    "features.index_auto_rebuild": "features_index_auto_rebuild",
    "features.auth_clearance_detectors": "features_auth_clearance_detectors",
    "chat.use_page_context_default": "chat_use_page_context_default",
    "browser.persist": "browser_persist",
    "browser.allow_cookies": "browser_allow_cookies",
    "dev.render_loop_guard": "dev_render_loop_guard",
    "sources.seed": "sources_seed",
    "setup.completed": "setup_completed",
}
_MODEL_TO_DB = {v: k for k, v in _DB_TO_MODEL.items()}


def _serialize(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, separators=(",", ":"))
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _deserialize(value: str) -> Any:
    try:
        return json.loads(value)
    except Exception:
        lowered = value.lower()
        if lowered in {"true", "false"}:
            return lowered == "true"
        return value


def read_config(conn: Connection) -> AppConfig:
    rows = conn.execute("SELECT k, v FROM app_config").fetchall()
    payload: dict[str, Any] = {}
    for row in rows:
        key = str(row["k"])
        value = str(row["v"])
        model_key = _DB_TO_MODEL.get(key)
        if not model_key:
            continue
        payload[model_key] = _deserialize(value)
    return AppConfig(**payload)


def write_config(conn: Connection, config: AppConfig) -> None:
    document = config.model_dump()
    for model_key, value in document.items():
        db_key = _MODEL_TO_DB[model_key]
        conn.execute(
            """
            INSERT INTO app_config(k, v)
            VALUES(?, ?)
            ON CONFLICT(k) DO UPDATE SET
              v = excluded.v,
              updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')
            """,
            (db_key, _serialize(value)),
        )


__all__ = ["read_config", "write_config"]
