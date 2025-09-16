#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from config import data_dir, load_config
from crawler.frontier import FrontierDB
from crawler.seeds import seed_frontier


def run_scrapy() -> None:
    subprocess.run([sys.executable, "-m", "scrapy", "crawl", "frontier"], cwd="crawler", check=True)


def command_crawl(args: argparse.Namespace) -> None:
    cfg = load_config()
    with FrontierDB(Path(cfg["crawler"]["frontier_db"]).expanduser().resolve(), cfg["crawler"]["per_domain_page_cap"], cfg["crawler"]["max_pages_total"]) as frontier:
        seed_frontier(frontier, cfg)
    run_scrapy()


def command_sitemapseed(args: argparse.Namespace) -> None:
    cfg = load_config()
    with FrontierDB(Path(cfg["crawler"]["frontier_db"]).expanduser().resolve(), cfg["crawler"]["per_domain_page_cap"], cfg["crawler"]["max_pages_total"]) as frontier:
        stats = seed_frontier(frontier, cfg)
        print(json.dumps(stats, indent=2))


def command_index(args: argparse.Namespace) -> None:
    import index_build

    if args.mode == "full":
        index_build.main(["full"])
    else:
        index_build.main(["update"])


def command_serve(args: argparse.Namespace) -> None:
    from app.main import create_app

    cfg = load_config()
    app = create_app(cfg)
    app.run(host=cfg["ui"]["host"], port=int(cfg["ui"]["port"]), debug=False)


def command_stats(args: argparse.Namespace) -> None:
    cfg = load_config()
    stats_path = data_dir(cfg) / "crawl_stats.json"
    if not stats_path.exists():
        print("No crawl stats available. Run a crawl first.")
        return
    print(stats_path.read_text(encoding="utf-8"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage the self-hosted search engine")
    sub = parser.add_subparsers(dest="command")

    crawl = sub.add_parser("crawl", help="Run the Scrapy frontier crawler")
    crawl.set_defaults(func=command_crawl)

    sitemapseed = sub.add_parser("sitemapseed", help="Ingest sitemap URLs into the frontier")
    sitemapseed.set_defaults(func=command_sitemapseed)

    index = sub.add_parser("index", help="Build or update the Whoosh index")
    index.add_argument("mode", choices=["full", "update"], help="Indexing mode")
    index.set_defaults(func=command_index)

    serve = sub.add_parser("serve", help="Run the Flask UI")
    serve.set_defaults(func=command_serve)

    stats = sub.add_parser("stats", help="Show crawl statistics")
    stats.set_defaults(func=command_stats)

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
