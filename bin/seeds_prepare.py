#!/usr/bin/env python3
"""Generate curated seed URLs and merge them into the seed store."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from seed_loader.curate import load_and_curate, write_curated
from search.seeds import DEFAULT_SEEDS_PATH, merge_curated_seeds


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Curate crawl seeds")
    parser.add_argument(
        "--hosts",
        nargs="*",
        help="Optional list of curated hosts used when loading sitemap sources",
    )
    parser.add_argument(
        "--curated-path",
        default="data/seeds/curated_seeds.jsonl",
        help="Output JSONL file for curated seeds",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    curated = load_and_curate(args.hosts)
    output_path = write_curated(curated, Path(args.curated_path))
    merged = merge_curated_seeds(output_path, store_path=DEFAULT_SEEDS_PATH)
    print(f"Wrote {len(curated)} curated seed(s) -> {output_path}")
    print(f"Merged {merged} domain entries into {DEFAULT_SEEDS_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
