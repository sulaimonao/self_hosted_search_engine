#!/usr/bin/env python3
"""Convenience wrapper around the Scrapy crawler."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import List, Sequence

from scrapy.crawler import CrawlerProcess

from crawler.settings import build_settings
from crawler.spiders.generic_spider import GenericSpider


def _as_bool(value: str | bool | None, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _load_seeds(seeds_file: Path) -> List[str]:
    if not seeds_file.exists():
        return []
    with seeds_file.open("r", encoding="utf-8") as handle:
        return [line.strip() for line in handle if line.strip() and not line.strip().startswith("#")]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Scrapy crawler")
    parser.add_argument("--seed", action="append", help="Seed URL to crawl", dest="seeds")
    parser.add_argument("--seeds-file", type=Path, help="File containing one seed URL per line")
    parser.add_argument("--store", type=Path, default=Path(os.getenv("CRAWL_STORE", "./data/crawl")))
    parser.add_argument("--max-pages", type=int, default=int(os.getenv("CRAWL_MAX_PAGES", "100")))
    parser.add_argument(
        "--respect-robots",
        dest="respect_robots",
        action="store_true",
        default=_as_bool(os.getenv("CRAWL_RESPECT_ROBOTS"), True),
        help="Respect robots.txt",
    )
    parser.add_argument(
        "--no-respect-robots",
        dest="respect_robots",
        action="store_false",
        help="Ignore robots.txt",
    )
    parser.add_argument(
        "--use-playwright",
        dest="use_playwright",
        action="store_true",
        default=_as_bool(os.getenv("CRAWL_USE_PLAYWRIGHT"), False),
        help="Enable Playwright rendering for every request",
    )
    parser.add_argument(
        "--allow-list",
        dest="allow_list",
        help="Comma separated substrings that URLs must match",
        default=os.getenv("CRAWL_ALLOW_LIST"),
    )
    parser.add_argument(
        "--deny-list",
        dest="deny_list",
        help="Comma separated substrings that URLs must not match",
        default=os.getenv("CRAWL_DENY_LIST"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    seeds: List[str] = []
    env_seed = os.getenv("URL")
    if env_seed:
        seeds.append(env_seed.strip())
    if args.seeds:
        seeds.extend(args.seeds)

    seeds_file = args.seeds_file or Path(os.getenv("SEEDS_FILE", "crawler/seeds.txt"))
    seeds.extend(_load_seeds(seeds_file))

    seeds = [s for s in seeds if s]
    if not seeds:
        raise SystemExit("No seeds provided. Use --seed or create crawler/seeds.txt")

    allow_list: Sequence[str] = []
    if args.allow_list:
        allow_list = [part.strip() for part in args.allow_list.split(",") if part.strip()]
    deny_list: Sequence[str] = []
    if args.deny_list:
        deny_list = [part.strip() for part in args.deny_list.split(",") if part.strip()]

    settings = build_settings(args.store, respect_robots=args.respect_robots, use_playwright=args.use_playwright)
    process = CrawlerProcess(settings=settings)
    process.crawl(
        GenericSpider,
        seeds=seeds,
        crawl_store=str(args.store),
        max_pages=args.max_pages,
        allow_list=allow_list,
        deny_list=deny_list,
        use_playwright=args.use_playwright,
    )
    process.start()


if __name__ == "__main__":
    main()
