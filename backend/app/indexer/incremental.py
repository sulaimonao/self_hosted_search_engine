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

from rank.authority import AuthorityIndex

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


_FIELD_BOOL_OPTIONS = ("stored", "unique", "sortable", "spelling", "scorable")


def _field_signature(field) -> Tuple:
    analyzer = getattr(field, "analyzer", None)
    analyzer_type = analyzer.__class__ if analyzer is not None else None
    fmt = getattr(field, "format", None)
    fmt_type = fmt.__class__ if fmt is not None else None
    bool_options = tuple(bool(getattr(field, option, False)) for option in _FIELD_BOOL_OPTIONS)
    return (
        field.__class__,
        bool_options,
        getattr(field, "vector", None),
        getattr(field, "field_boost", 1.0),
        fmt_type,
        analyzer_type,
    )


def _schema_migration_reason(current_schema, desired_schema) -> str | None:
    current_fields = set(current_schema.names())
    missing = REQUIRED_FIELDS - current_fields
    if missing:
        return f"missing required fields: {', '.join(sorted(missing))}"
    for field_name in REQUIRED_FIELDS:
        current_field = current_schema[field_name]
        desired_field = desired_schema[field_name]
        if _field_signature(current_field) != _field_signature(desired_field):
            return f"incompatible field definition for '{field_name}'"
    return None


def _clear_index_dir(index_dir: Path) -> None:
    for entry in index_dir.iterdir():
        if entry.is_dir():
            shutil.rmtree(entry)
        else:
            entry.unlink()


def ensure_index(index_dir: Path):
    index_dir.mkdir(parents=True, exist_ok=True)
    schema = build_schema()
    if index.exists_in(index_dir):
        ix = index.open_dir(index_dir)
        try:
            reason = _schema_migration_reason(ix.schema, schema)
        except Exception:
            LOGGER.warning("failed to inspect existing index schema at %s; rebuilding", index_dir, exc_info=True)
            reason = "schema inspection failed"
        if reason is None:
            return ix
        LOGGER.warning(
            "rebuilding search index at %s due to schema change (%s); legacy documents will be re-indexed on the next crawl",
            index_dir,
            reason,
        )
        ix.close()
        _clear_index_dir(index_dir)
        return index.create_in(index_dir, schema)
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
    authority = AuthorityIndex.load_default()
    writer = ix.writer(limitmb=256)
    indexed_docs: list[Mapping[str, str]] = []
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
            indexed_docs.append(doc)
    finally:
        writer.commit()

    _write_json(ledger_path, ledger)
    sim_index.save(simhash_path)
    last_index_time_path.write_text(str(int(time.time())) + "\n", encoding="utf-8")
    authority.update_from_docs(indexed_docs)
    authority.save()
    total_docs = ix.doc_count()
    metrics.record_index_results(added, skipped, deduped, total_docs)
    LOGGER.info(
        "incremental index completed: added=%s skipped=%s deduped=%s total=%s",
        added,
        skipped,
        deduped,
        total_docs,
    )
    return added, skipped, deduped
