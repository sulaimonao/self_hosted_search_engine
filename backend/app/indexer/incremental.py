"""Incremental indexing pipeline with deduplication."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Iterable, Mapping, Tuple

from whoosh import index

from .dedupe import SimHashIndex, simhash64
from .schema import build_schema
from ..metrics import metrics

LOGGER = logging.getLogger(__name__)


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


def ensure_index(index_dir: Path):
    index_dir.mkdir(parents=True, exist_ok=True)
    if index.exists_in(index_dir):
        return index.open_dir(index_dir)
    schema = build_schema()
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
