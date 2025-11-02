"""Meta endpoints exposing server clocks, capabilities, and runtime metadata."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from flask import Blueprint, current_app, jsonify

from backend.app.services.runtime_status import build_capability_snapshot

from .schemas import ChatRequest, ChatResponsePayload, SearchResponsePayload

bp = Blueprint("meta_api", __name__, url_prefix="/api/meta")


def _capability_snapshot() -> dict[str, Any]:
    snapshot = build_capability_snapshot()
    diagnostics_enabled = (
        "diagnostics_api.diagnostics_endpoint" in current_app.view_functions
    )
    progress_stream_enabled = (
        "progress_stream.progress_stream" in current_app.view_functions
    )
    snapshot["diagnostics"] = diagnostics_enabled
    snapshot["progress_stream"] = progress_stream_enabled
    return snapshot


def _build_openapi_document() -> dict[str, Any]:
    chat_request_schema = ChatRequest.model_json_schema(
        ref_template="#/components/schemas/{model}"
    )
    chat_response_schema = ChatResponsePayload.model_json_schema(
        ref_template="#/components/schemas/{model}"
    )
    search_response_schema = SearchResponsePayload.model_json_schema(
        ref_template="#/components/schemas/{model}"
    )

    components = {
        "schemas": {
            "ChatRequest": chat_request_schema,
            "ChatResponse": chat_response_schema,
            "SearchResponse": search_response_schema,
        }
    }

    paths = {
        "/api/chat": {
            "post": {
                "summary": "Send a chat conversation to the local LLM",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/ChatRequest"}
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Structured assistant response",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/ChatResponse"}
                            },
                            "application/x-ndjson": {
                                "schema": {"type": "string"},
                                "description": "Newline-delimited JSON stream with metadata, deltas, and completion events.",
                            },
                        },
                    },
                    "400": {
                        "description": "Validation error",
                    },
                },
            }
        },
        "/api/search": {
            "get": {
                "summary": "Execute a search against the local index",
                "parameters": [
                    {
                        "name": "q",
                        "in": "query",
                        "required": True,
                        "schema": {"type": "string"},
                        "description": "Search query text.",
                    },
                    {
                        "name": "llm",
                        "in": "query",
                        "required": False,
                        "schema": {"type": "boolean"},
                        "description": "Enable LLM-backed reasoning pipeline.",
                    },
                    {
                        "name": "model",
                        "in": "query",
                        "required": False,
                        "schema": {"type": "string"},
                        "description": "Override LLM model when llm=1.",
                    },
                    {
                        "name": "page",
                        "in": "query",
                        "required": False,
                        "schema": {"type": "integer", "minimum": 1},
                        "description": "Result page for ship-it mode.",
                    },
                    {
                        "name": "size",
                        "in": "query",
                        "required": False,
                        "schema": {"type": "integer", "minimum": 1, "maximum": 50},
                        "description": "Page size for ship-it mode.",
                    },
                    {
                        "name": "shipit",
                        "in": "query",
                        "required": False,
                        "schema": {"type": "boolean"},
                        "description": "Return deterministic stubbed search data for integration tests.",
                    },
                ],
                "responses": {
                    "200": {
                        "description": "Search results",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/SearchResponse"
                                }
                            }
                        },
                    }
                },
            }
        },
    }

    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Self-Hosted Search Engine API",
            "version": "1.0.0",
            "description": "Local search, chat, and crawl orchestration endpoints.",
        },
        "servers": [{"url": "/"}],
        "paths": paths,
        "components": components,
    }


@bp.get("/health")
def health() -> tuple[Any, int]:
    payload = {
        "ok": True,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    return jsonify(payload), 200


@bp.get("/capabilities")
def capabilities() -> tuple[Any, int]:
    snapshot = _capability_snapshot()
    return jsonify(snapshot), 200


@bp.get("/openapi")
def openapi_document():
    return jsonify(_build_openapi_document()), 200


@bp.get("/time")
def server_time():
    now_utc = datetime.now(timezone.utc)
    local_now = datetime.now().astimezone()
    tz_name = local_now.tzname() or time.tzname[0]
    payload = {
        "server_time": local_now.isoformat(timespec="seconds"),
        "server_time_utc": now_utc.isoformat(timespec="seconds"),
        "server_timezone": tz_name,
        "epoch_ms": int(time.time() * 1000),
    }
    return jsonify(payload), 200


__all__ = ["bp"]
