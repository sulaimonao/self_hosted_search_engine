#!/usr/bin/env python3
"""Incrementally reindex normalized documents."""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from .reindex import run
except ImportError:  # pragma: no cover - fallback for direct execution
    from reindex import run


def main() -> None:
    run("incremental")


if __name__ == "__main__":
    sys.exit(main())
