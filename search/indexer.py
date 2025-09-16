"""Utilities for creating and updating the Whoosh index."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterable, Mapping

from whoosh import index
from whoosh.fields import ID, TEXT, Schema

LOGGER = logging.getLogger(__name__)


DEFAULT_SCHEMA = Schema(
    url=ID(stored=True, unique=True),
    title=TEXT(stored=True),
    text=TEXT(stored=True),
)


def create_or_open_index(index_dir: str):
    """Create the Whoosh index if missing and return an ``Index`` instance."""

    path = Path(index_dir)
    path.mkdir(parents=True, exist_ok=True)

    if index.exists_in(path):
        return index.open_dir(path)

    LOGGER.info("creating new index at %s", path)
    return index.create_in(path, DEFAULT_SCHEMA)


def index_documents(ix, docs: Iterable[Mapping[str, str]]) -> int:
    """Index the provided documents and return how many were stored."""

    count = 0
    writer = ix.writer(limitmb=256)
    try:
        for doc in docs:
            url = (doc.get("url") or "").strip()
            if not url:
                LOGGER.debug("skipping document without url: %s", doc)
                continue
            title = (doc.get("title") or "").strip()
            text = (doc.get("text") or "").strip()
            writer.update_document(url=url, title=title, text=text)
            count += 1
    finally:
        writer.commit()
    LOGGER.info("indexed %s document(s)", count)
    return count


def iter_normalized_documents(crawl_store: str):
    """Yield normalized crawl documents from ``normalized.jsonl`` if present."""

    path = Path(crawl_store) / "normalized.jsonl"
    if not path.exists():
        LOGGER.warning("normalized crawl data not found at %s", path)
        return
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError as exc:
                LOGGER.error("failed to parse line from %s: %s", path, exc)
                continue
            yield data
