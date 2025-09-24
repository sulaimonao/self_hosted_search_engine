#!/usr/bin/env python3
"""Sanity checks before starting the development server."""

from __future__ import annotations

import os
from pathlib import Path


def main() -> None:
    index_dir = Path(os.getenv("INDEX_DIR", "./data/whoosh"))
    crawl_store = Path(os.getenv("CRAWL_STORE", "./data/crawl"))
    normalized = Path(os.getenv("NORMALIZED_PATH", "./data/normalized/normalized.jsonl"))

    index_dir.mkdir(parents=True, exist_ok=True)
    (crawl_store / "raw").mkdir(parents=True, exist_ok=True)
    normalized.parent.mkdir(parents=True, exist_ok=True)

    if normalized.exists():
        print(f"✅ Found crawl data: {normalized}")
    else:
        print(f"⚠️ No normalized crawl data at {normalized}. Run make crawl && make reindex once ready.")

    if not any(index_dir.iterdir()):
        print(f"⚠️ Index directory {index_dir} is empty. Searches will return no results until you run make reindex.")
    else:
        print(f"✅ Index directory ready at {index_dir}.")


if __name__ == "__main__":
    main()
