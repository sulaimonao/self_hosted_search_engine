#!/usr/bin/env python3
"""Rebuild the Whoosh index from normalized crawl data."""

from __future__ import annotations

import itertools
import os
import shutil
from pathlib import Path

from search.indexer import create_or_open_index, index_documents, iter_normalized_documents


def main() -> None:
    index_dir = Path(os.getenv("INDEX_DIR", "./data/index"))
    crawl_store = Path(os.getenv("CRAWL_STORE", "./data/crawl"))

    if index_dir.exists():
        shutil.rmtree(index_dir)
    index_dir.mkdir(parents=True, exist_ok=True)

    ix = create_or_open_index(str(index_dir))
    docs_iter = iter_normalized_documents(str(crawl_store))
    first = next(docs_iter, None)
    if first is None:
        print(f"No normalized crawl data found in {crawl_store}. Nothing to index.")
        return
    indexed = index_documents(ix, itertools.chain([first], docs_iter))
    print(f"Indexed {indexed} document(s) into {index_dir}")


if __name__ == "__main__":
    main()
