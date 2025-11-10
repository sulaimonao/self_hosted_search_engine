"""Lightweight database inspection API for read-only queries."""

from __future__ import annotations

from typing import Any

from flask import Blueprint, current_app, jsonify, request

from backend.app.db import AppStateDB

bp = Blueprint("db_api", __name__, url_prefix="/api/db")

_NAMED_QUERIES: dict[str, str] = {
    "app_config": "SELECT k, v FROM app_config ORDER BY k LIMIT 200",
    "history_recent": (
        "SELECT id, url, title, visited_at, status_code, shadow_enqueued "
        "FROM history ORDER BY visited_at DESC LIMIT 50"
    ),
    "crawl_jobs": (
        "SELECT id, query, status, enqueued_at, finished_at FROM crawl_jobs "
        "ORDER BY enqueued_at DESC LIMIT 25"
    ),
}

_DISALLOWED_TOKENS = {"insert", "update", "delete", "drop", "alter", "create", "attach", "detach", "reindex", "vacuum", "replace"}


def _serialize_cell(value: Any) -> Any:
    if isinstance(value, (bytes, bytearray)):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return value.hex()
    if isinstance(value, memoryview):
        return _serialize_cell(value.tobytes())
    return value


def _prepare_sql(sql: str) -> str:
    trimmed = sql.strip()
    if trimmed.endswith(";"):
        trimmed = trimmed[:-1].strip()
    return trimmed


def _is_safe_sql(sql: str) -> bool:
    lowered = sql.lower()
    if not lowered:
        return False
    if lowered.startswith("pragma "):
        return "table_info" in lowered
    if lowered.startswith("select") or lowered.startswith("with"):
        return not any(token in lowered for token in _DISALLOWED_TOKENS)
    return False


@bp.post("/query")
def run_query():
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"error": "invalid_payload"}), 400

    named = str(payload.get("named_query") or payload.get("namedQuery") or "").strip()
    sql_value = str(payload.get("sql") or "").strip()
    if named:
        sql_template = _NAMED_QUERIES.get(named)
        if not sql_template:
            return jsonify({"error": "unknown_named_query", "allowed": sorted(_NAMED_QUERIES)}), 400
        sql_value = sql_template
    if not sql_value:
        return jsonify({"error": "query_required"}), 400

    sql = _prepare_sql(sql_value)
    if not _is_safe_sql(sql):
        return jsonify({"error": "unsafe_query"}), 400

    state_db = current_app.config.get("APP_STATE_DB")
    if not isinstance(state_db, AppStateDB):
        return jsonify({"error": "db_unavailable"}), 503

    rows: list[list[Any]] = []
    columns: list[str] = []
    truncated = False
    with state_db._lock, state_db._conn:  # type: ignore[attr-defined]
        cursor = state_db._conn.execute(sql)  # type: ignore[attr-defined]
        if cursor.description:
            columns = [col[0] for col in cursor.description]
        for index, row in enumerate(cursor):
            if index >= 200:
                truncated = True
                break
            if columns:
                rows.append([_serialize_cell(row[column]) for column in columns])
            else:
                rows.append([_serialize_cell(value) for value in row])

    response = {
        "rows": rows,
        "columns": columns,
        "rowCount": len(rows),
        "truncated": truncated,
        "namedQuery": named or None,
    }
    return jsonify(response)


__all__ = ["bp", "run_query"]
