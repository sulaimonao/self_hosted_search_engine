#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from config import load_config
from crawler.frontier import FrontierDB
from crawler.seeds import seed_frontier


def with_frontier():
    cfg = load_config()
    frontier_path = Path(cfg["crawler"]["frontier_db"]).expanduser().resolve()
    return FrontierDB(frontier_path, cfg["crawler"]["per_domain_page_cap"], cfg["crawler"]["max_pages_total"])


def cmd_stats(args: argparse.Namespace) -> None:
    with with_frontier() as frontier:
        print(json.dumps(frontier.stats(), indent=2))


def cmd_clear(args: argparse.Namespace) -> None:
    with with_frontier() as frontier:
        frontier.clear()
        print("Frontier cleared.")


def cmd_export(args: argparse.Namespace) -> None:
    output = Path(args.output)
    with with_frontier() as frontier, output.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["url", "depth", "status", "domain", "use_js"])
        for row in frontier.iter_all():
            writer.writerow([row["url"], row["depth"], row["status"], row["domain"], row["use_js"]])
        print(f"Exported frontier to {output}")


def cmd_seed(args: argparse.Namespace) -> None:
    cfg = load_config()
    with with_frontier() as frontier:
        stats = seed_frontier(frontier, cfg)
        print(json.dumps(stats, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Frontier maintenance tool")
    sub = parser.add_subparsers(dest="command")

    sub_stats = sub.add_parser("stats", help="Show frontier status")
    sub_stats.set_defaults(func=cmd_stats)

    sub_clear = sub.add_parser("clear", help="Clear all pending URLs")
    sub_clear.set_defaults(func=cmd_clear)

    sub_export = sub.add_parser("export", help="Export frontier to CSV")
    sub_export.add_argument("output", help="CSV output path")
    sub_export.set_defaults(func=cmd_export)

    sub_seed = sub.add_parser("seed", help="Seed URLs from config")
    sub_seed.set_defaults(func=cmd_seed)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        parser.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()
