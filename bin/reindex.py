#!/usr/bin/env python3
"""Rebuild or incrementally update the Whoosh index."""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import sys
import time
from pathlib import Path
from typing import Iterable, List

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from backend.app.config import AppConfig
    from backend.app.indexer.incremental import incremental_index
except ModuleNotFoundError as exc:  # pragma: no cover - defensive path hints
    if exc.name == "backend":
        msg = (
            "Unable to import 'backend'. Ensure the repository root is on PYTHONPATH or "
            "invoke this script via 'python -m bin.reindex'."
        )
        print(msg, file=sys.stderr)
    raise

INDEX_INC_WINDOW_MIN = int(os.getenv("INDEX_INC_WINDOW_MIN", "60"))


def _load_docs(path: Path, *, window_minutes: int | None) -> List[dict]:
    if not path.exists():
        raise FileNotFoundError(f"Normalized data not found at {path}")
    cutoff: float | None = None
    if window_minutes and window_minutes > 0:
        cutoff = time.time() - (window_minutes * 60)
    docs: List[dict] = []
    seen_hashes: set[str] = set()
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                continue
            if cutoff is not None:
                fetched = payload.get("fetched_at")
                try:
                    fetched_ts = float(fetched)
                except (TypeError, ValueError):
                    fetched_ts = 0.0
                if fetched_ts < cutoff:
                    continue
            content_hash = payload.get("content_hash")
            if isinstance(content_hash, str) and content_hash:
                if content_hash in seen_hashes:
                    continue
                seen_hashes.add(content_hash)
            docs.append(payload)
    return docs


def _rebuild_index(config: AppConfig, docs: Iterable[dict]) -> None:
    if config.index_dir.exists():
        shutil.rmtree(config.index_dir)
    config.index_dir.mkdir(parents=True, exist_ok=True)
    incremental_index(
        config.index_dir,
        config.ledger_path,
        config.simhash_path,
        config.last_index_time_path,
        docs,
    )


def run(mode: str) -> None:
    config = AppConfig.from_env()
    config.ensure_dirs()
    normalized = config.normalized_path

    if mode == "incremental":
        docs = _load_docs(normalized, window_minutes=INDEX_INC_WINDOW_MIN)
        if not docs:
            print("No new documents within incremental window; skipping reindex.")
            return
        incremental_index(
            config.index_dir,
            config.ledger_path,
            config.simhash_path,
            config.last_index_time_path,
            docs,
        )
    else:
        docs = _load_docs(normalized, window_minutes=None)
        _rebuild_index(config, docs)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reindex Whoosh data store")
    parser.add_argument(
        "--mode",
        choices={"incremental", "full"},
        default="incremental",
        help="Choose between incremental (default) or full rebuild",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        run(args.mode)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
