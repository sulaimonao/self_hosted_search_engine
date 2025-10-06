"""Scrapy settings builder used by :mod:`bin.crawl`."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Any

DEFAULT_USER_AGENT = os.getenv(
    "CRAWL_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
)


def _as_bool(value: str | bool | None, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def build_settings(
    crawl_store: Path,
    respect_robots: bool,
    use_playwright: bool,
) -> Dict[str, Any]:
    """Return Scrapy settings tuned for local crawling."""

    crawl_store.mkdir(parents=True, exist_ok=True)

    settings: Dict[str, Any] = {
        "BOT_NAME": "self_hosted_search_engine",
        "ROBOTSTXT_OBEY": respect_robots,
        "LOG_LEVEL": os.getenv("CRAWL_LOG_LEVEL", "INFO"),
        "USER_AGENT": DEFAULT_USER_AGENT,
        "DOWNLOAD_DELAY": float(os.getenv("CRAWL_DOWNLOAD_DELAY", "0.25")),
        "CONCURRENT_REQUESTS": int(os.getenv("CRAWL_CONCURRENT_REQUESTS", "8")),
        "CONCURRENT_REQUESTS_PER_DOMAIN": int(os.getenv("CRAWL_CONCURRENT_PER_DOMAIN", "4")),
        "AUTOTHROTTLE_ENABLED": _as_bool(os.getenv("CRAWL_AUTOTHROTTLE"), True),
        "FEED_EXPORT_ENCODING": "utf-8",
        "ITEM_PIPELINES": {"crawler.pipelines.NormalizePipeline": 300},
        "DOWNLOADER_MIDDLEWARES": {
            "crawler.middlewares.AdaptiveDelayMiddleware": 850,
        },
    }

    if use_playwright:
        settings.update(
            {
                "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
                "PLAYWRIGHT_BROWSER_TYPE": os.getenv("PLAYWRIGHT_BROWSER_TYPE", "chromium"),
                "DOWNLOAD_HANDLERS": {
                    "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
                    "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
                },
                "PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT": int(
                    os.getenv("PLAYWRIGHT_NAVIGATION_TIMEOUT", "30000")
                ),
            }
        )
    return settings
