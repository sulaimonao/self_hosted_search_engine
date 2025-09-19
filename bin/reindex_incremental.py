#!/usr/bin/env python3
"""Incrementally reindex normalized documents."""

from __future__ import annotations

import json
import sys

from backend.app.config import AppConfig
from backend.app.indexer.incremental import incremental_index


def load_normalized(path):
    docs = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    docs.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    print(f"Skipping invalid JSON line: {exc}", file=sys.stderr)
    except FileNotFoundError:
        print(f"Normalized data not found at {path}. Run bin/normalize.py first.", file=sys.stderr)
        sys.exit(1)
    return docs


def main() -> None:
    config = AppConfig.from_env()
    config.ensure_dirs()
    docs = load_normalized(config.normalized_path)
    added, skipped, deduped = incremental_index(
        config.index_dir,
        config.ledger_path,
        config.simhash_path,
        config.last_index_time_path,
        docs,
    )
    print(
        "Incremental index complete: "
        f"added={added} skipped={skipped} deduped={deduped} -> {config.index_dir}"
    )


if __name__ == "__main__":
    sys.exit(main())
