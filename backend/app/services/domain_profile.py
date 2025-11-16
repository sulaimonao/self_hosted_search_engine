"""Placeholder domain profile helpers for development/test environments."""

from __future__ import annotations

from typing import Any


def _require(value: str | None, field: str) -> str:
    if not value:
        raise ValueError(f"{field} is required")
    return value


def get_snapshot(host: str) -> dict[str, Any]:
    target = _require(host, "host")
    return {"host": target, "pages": []}


def get_graph(host: str, *, limit: int = 150) -> dict[str, Any]:
    target = _require(host, "host")
    return {"host": target, "limit": int(limit), "edges": []}


def ingest_sample(payload: dict[str, Any] | None) -> dict[str, Any]:
    data = payload or {}
    host = _require(data.get("host"), "host")
    return {"host": host, "ingested": True}


def get_page_snapshot(url: str) -> dict[str, Any]:
    target = _require(url, "url")
    return {"url": target, "content": None}


__all__ = [
    "get_snapshot",
    "get_graph",
    "get_page_snapshot",
    "ingest_sample",
]
