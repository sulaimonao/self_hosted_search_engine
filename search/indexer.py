"""Compatibility helpers for creating the Whoosh index."""

from __future__ import annotations

from pathlib import Path

from backend.app.indexer.incremental import ensure_index


def create_or_open_index(index_dir: str):
    return ensure_index(Path(index_dir))
