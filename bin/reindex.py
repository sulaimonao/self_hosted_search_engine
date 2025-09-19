#!/usr/bin/env python3
"""Backward-compatible entry point for incremental indexing."""

from __future__ import annotations

import sys

from reindex_incremental import main as incremental_main  # type: ignore[import-not-found]


if __name__ == "__main__":
    sys.exit(incremental_main())
