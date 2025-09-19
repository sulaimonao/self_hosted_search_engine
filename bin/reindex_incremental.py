#!/usr/bin/env python3
"""Incrementally reindex normalized documents."""

from __future__ import annotations

import sys

def main() -> None:
    from reindex import run

    run("incremental")


if __name__ == "__main__":
    sys.exit(main())
