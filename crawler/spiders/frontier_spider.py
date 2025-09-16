from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List

import scrapy
from scrapy import Request
from scrapy.http import Response

from config import data_dir, load_config
from crawler.frontier import FrontierDB
from crawler.items import PageItem
from crawler.seeds import seed_frontier
from crawler.utils import (
    canonical_link_priority,
    extract_text,
    join_url,
    normalize_url,
    now_utc,
    url_domain,
)


logger = logging.getLogger(__name__)


class FrontierSpider(scrapy.Spider):
    name = "frontier"

    custom_settings = {
        "DEPTH_PRIORITY": 1,
        "SCHEDULER_DISK_QUEUE": "scrapy.squeues.PickleFifoDiskQueue",
        "SCHEDULER_MEMORY_QUEUE": "scrapy.squeues.FifoMemoryQueue",
        "LOG_LEVEL": "INFO",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.config = load_config()
        self.crawler_cfg = self.config["crawler"]
        self.base_dir = data_dir(self.config)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        frontier_path = Path(self.crawler_cfg["frontier_db"]).expanduser().resolve()
        self.frontier = FrontierDB(
            frontier_path,
            per_domain_cap=self.crawler_cfg["per_domain_page_cap"],
            max_total=self.crawler_cfg["max_pages_total"],
        )
        self.allowed_domains_set = set()
        self.depth_limit = self.crawler_cfg.get("depth_limit", 2)
        self.start_time = datetime.now(timezone.utc)
        self.page_stats = {
            "started_at": self.start_time.isoformat(),
            "pages_fetched": 0,
            "pages_failed": 0,
            "bytes": 0,
            "domains": {},
            "latency_total": 0.0,
        }

    def start_requests(self) -> Iterable[Request]:
        self.frontier.reset_in_progress()
        seed_frontier(self.frontier, self.config)
        self.allowed_domains_set = self.frontier.distinct_domains()
        batch = list(self.frontier.next_entries(self.crawler_cfg["concurrent_requests"]))
        if not batch:
            self.logger.warning("No URLs enqueued; populate seeds or frontier")
        for entry in batch:
            yield self._make_request(entry)

    def _make_request(self, entry) -> Request:
        headers = {"User-Agent": self.crawler_cfg["user_agent"]}
        meta = {"depth": entry.depth, "frontier_entry": entry, "render_js": entry.use_js}
        if entry.use_js:
            meta["playwright"] = True
            meta["playwright_include_page"] = False
        return Request(entry.url, callback=self.parse, errback=self.handle_error, dont_filter=True, headers=headers, meta=meta)

    def _schedule_from_frontier(self, limit: int = 1) -> List[Request]:
        scheduled: List[Request] = []
        for entry in self.frontier.next_entries(limit):
            scheduled.append(self._make_request(entry))
        return scheduled

    def parse(self, response: Response):
        entry = response.meta.get("frontier_entry")
        if entry:
            self.frontier.mark_fetched(entry.url)
        domain = url_domain(response.url)
        self.allowed_domains_set.add(domain)
        title = response.xpath("//title/text()").get(default="").strip()
        body_html = response.text
        text = extract_text(body_html)
        item = PageItem(
            url=normalize_url(response.url),
            title=title,
            html=body_html,
            text=text,
            domain=domain,
            fetched_at=now_utc(),
        )
        yield item

        self.page_stats["pages_fetched"] += 1
        self.page_stats["bytes"] += len(response.body)
        self.page_stats["domains"].setdefault(domain, 0)
        self.page_stats["domains"][domain] += 1
        latency = float(response.meta.get("download_latency") or 0.0)
        self.page_stats["latency_total"] += latency

        depth = entry.depth if entry else 0
        if depth < self.depth_limit:
            links = self._extract_links(response)
            for url in links:
                self.frontier.enqueue(url, depth=depth + 1)
        use_js = bool(getattr(entry, "use_js", False))
        if self.crawler_cfg["use_js_fallback"] and not use_js and len(text) < self.crawler_cfg["js_fallback_threshold_chars"]:
            self.frontier.enqueue(response.url, depth=depth, use_js=True)
        yield from self._schedule_from_frontier()

    def _extract_links(self, response: Response) -> List[str]:
        candidate_urls = []
        base_url = response.url
        for href in response.css("a::attr(href)").getall():
            if href.startswith("javascript:") or href.startswith("mailto:"):
                continue
            candidate = join_url(base_url, href)
            domain = url_domain(candidate)
            if self.allowed_domains_set and domain not in self.allowed_domains_set:
                continue
            candidate_urls.append(candidate)
        ordered = canonical_link_priority(candidate_urls)
        return ordered

    def handle_error(self, failure):
        request = failure.request
        entry = request.meta.get("frontier_entry")
        if entry:
            self.frontier.mark_failed(entry.url, failure.getErrorMessage())
        self.page_stats["pages_failed"] += 1
        self.logger.error("Failed to fetch %s: %s", request.url, failure.getErrorMessage())
        yield from self._schedule_from_frontier()

    def closed(self, reason: str) -> None:
        stats_path = self.base_dir / "crawl_stats.json"
        finished_at = datetime.now(timezone.utc)
        self.page_stats["finished_at"] = finished_at.isoformat()
        self.page_stats["reason"] = reason
        fetched = self.page_stats.get("pages_fetched", 0) or 1
        self.page_stats["avg_latency_sec"] = self.page_stats["latency_total"] / fetched
        self.page_stats["duration_sec"] = (finished_at - self.start_time).total_seconds()
        self.page_stats.pop("latency_total", None)
        with stats_path.open("w", encoding="utf-8") as fh:
            json.dump(self.page_stats, fh, indent=2)
        self.frontier.close()
