"""Incremental indexing pipeline with deduplication."""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import time
from pathlib import Path
from typing import Iterable, Mapping, Tuple

from whoosh import index
from whoosh.analysis import CompositeAnalyzer

from .dedupe import SimHashIndex, simhash64
from .schema import build_schema
from ..metrics import metrics

LOGGER = logging.getLogger(__name__)

REQUIRED_FIELDS = {"url", "lang", "title", "h1h2", "body"}


def _content_hash(doc: Mapping[str, str]) -> str:
    payload = "\u0001".join([doc.get("title", ""), doc.get("h1h2", ""), doc.get("body", "")])
    return hashlib.sha256(payload.encode("utf-8", errors="ignore")).hexdigest()


def _load_json(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text("utf-8"))
    except Exception:
        LOGGER.warning("unable to parse ledger at %s", path)
        return {}


def _write_json(path: Path, payload: dict[str, str]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _field_compatible(current_field, expected_field) -> bool:
    """Return True when the current field matches the expected schema."""

    if current_field.__class__ is not expected_field.__class__:
        return False

    for attr in ("stored", "unique", "scorable", "vector"):
        if getattr(current_field, attr, None) != getattr(expected_field, attr, None):
            return False

    current_phrase = getattr(current_field, "phrase", None)
    expected_phrase = getattr(expected_field, "phrase", None)
    if current_phrase != expected_phrase:
        return False

    current_analyzer = getattr(current_field, "analyzer", None)
    expected_analyzer = getattr(expected_field, "analyzer", None)
    if bool(current_analyzer) != bool(expected_analyzer):
        return False
    if expected_analyzer is not None:
        if current_analyzer.__class__ is not expected_analyzer.__class__:
            return False
        if isinstance(expected_analyzer, CompositeAnalyzer):
            expected_components = tuple(type(component) for component in expected_analyzer)
            current_components = tuple(type(component) for component in current_analyzer)
            if current_components != expected_components:
                return False
    return True


def _schema_needs_migration(existing_schema, expected_schema) -> bool:
    existing_fields = set(existing_schema.names())
    if not REQUIRED_FIELDS.issubset(existing_fields):
        return True

    for field_name in REQUIRED_FIELDS:
        if not _field_compatible(existing_schema[field_name], expected_schema[field_name]):
            return True
    return False


def _clear_directory(path: Path) -> None:
    for child in path.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def ensure_index(index_dir: Path):
    index_dir.mkdir(parents=True, exist_ok=True)
    schema = build_schema()
    if index.exists_in(index_dir):
        ix = index.open_dir(index_dir)
        if _schema_needs_migration(ix.schema, schema):
            LOGGER.warning(
                "detected legacy Whoosh schema at %s; rebuilding index with the current definition",
                index_dir,
            )
            ix.close()
            _clear_directory(index_dir)
            index_dir.mkdir(parents=True, exist_ok=True)
            return index.create_in(index_dir, schema)
        return ix
    return index.create_in(index_dir, schema)


def incremental_index(
    index_dir: Path,
    ledger_path: Path,
    simhash_path: Path,
    last_index_time_path: Path,
    docs: Iterable[Mapping[str, str]],
) -> Tuple[int, int, int]:
    """Index the provided documents incrementally.

    Returns a tuple ``(added, skipped, deduped)``.
    """

    ix = ensure_index(index_dir)
    ledger = _load_json(ledger_path)
    sim_index = SimHashIndex.load(simhash_path)

    added = skipped = deduped = 0
    writer = ix.writer(limitmb=256)
    try:
        for doc in docs:
            url = (doc.get("url") or "").strip()
            body = (doc.get("body") or "").strip()
            if not url or not body:
                skipped += 1
                continue
            signature = _content_hash(doc)
            previous_signature = ledger.get(url)
            if previous_signature == signature:
                skipped += 1
                continue
            sim_signature = simhash64(body)
            duplicate_url = sim_index.nearest(sim_signature, threshold=3)
            if duplicate_url and duplicate_url != url:
                ledger[url] = signature
                deduped += 1
                continue
            writer.update_document(
                url=url,
                title=doc.get("title", ""),
                h1h2=doc.get("h1h2", ""),
                body=body,
                lang=doc.get("lang", "unknown"),
            )
            ledger[url] = signature
            sim_index.update(url, sim_signature)
            added += 1
    finally:
        writer.commit()

    _write_json(ledger_path, ledger)
    sim_index.save(simhash_path)
    last_index_time_path.write_text(str(int(time.time())) + "\n", encoding="utf-8")
    metrics.record_index_results(added, skipped, deduped)
    LOGGER.info("incremental index completed: added=%s skipped=%s deduped=%s", added, skipped, deduped)
    return added, skipped, deduped
