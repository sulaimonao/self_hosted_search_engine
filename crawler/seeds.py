from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from config import load_config
from crawler.frontier import FrontierDB
from crawler.sitemaps import collect_sitemap_urls
from crawler.utils import normalize_url


def _read_lines(path: Path) -> List[str]:
    if not path.exists():
        return []
    lines = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            value = line.strip()
            if not value or value.startswith("#"):
                continue
            lines.append(value)
    return lines


def seed_frontier(frontier: FrontierDB, config: dict | None = None) -> Dict[str, int]:
    cfg = config or load_config()
    stats: Dict[str, int] = {"urls": 0, "domains": 0, "sitemaps": 0}

    seeds_cfg = cfg["seeds"]
    crawler_cfg = cfg["crawler"]
    urls_path = Path(seeds_cfg["urls_file"]).expanduser().resolve()
    for raw_url in _read_lines(urls_path):
        if frontier.enqueue(raw_url, depth=0):
            stats["urls"] += 1

    domains_path = Path(seeds_cfg["domains_file"]).expanduser().resolve()
    for domain in _read_lines(domains_path):
        url = normalize_url(f"https://{domain.strip('/')}/")
        if frontier.enqueue(url, depth=0):
            stats["domains"] += 1

    sitemaps_path = Path(seeds_cfg["sitemaps_file"]).expanduser().resolve()
    sitemap_urls = _read_lines(sitemaps_path)
    if sitemap_urls:
        discovered = collect_sitemap_urls(
            sitemap_urls,
            user_agent=crawler_cfg["user_agent"],
            per_domain_cap=crawler_cfg["per_domain_page_cap"],
        )
        for url in discovered:
            if frontier.enqueue(url, depth=1):
                stats["sitemaps"] += 1
    return stats
