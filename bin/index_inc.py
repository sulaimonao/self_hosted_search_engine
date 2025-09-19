#!/usr/bin/env python3
"""Run incremental indexing on a schedule."""

from __future__ import annotations

import argparse
import os
import sys
import time

from reindex import run as run_reindex

INDEX_INC_WINDOW_MIN = int(os.getenv("INDEX_INC_WINDOW_MIN", "60"))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Incremental indexing loop")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single incremental pass and exit",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=INDEX_INC_WINDOW_MIN,
        help="Number of minutes to wait between incremental passes",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    interval = max(1, args.interval)
    while True:
        run_reindex("incremental")
        if args.once:
            break
        time.sleep(interval * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
