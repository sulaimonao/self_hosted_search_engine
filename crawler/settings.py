"""Scrapy settings derived from config.yaml."""
from __future__ import annotations

from pathlib import Path

from config import data_dir, load_config

cfg = load_config()

BOT_NAME = "crawler"
SPIDER_MODULES = ["crawler.spiders"]
NEWSPIDER_MODULE = "crawler.spiders"

USER_AGENT = cfg["crawler"]["user_agent"]
ROBOTSTXT_OBEY = cfg["crawler"].get("obey_robots", True)
DOWNLOAD_DELAY = cfg["crawler"].get("download_delay_sec", 0.5)
CONCURRENT_REQUESTS = cfg["crawler"].get("concurrent_requests", 8)
CONCURRENT_REQUESTS_PER_DOMAIN = cfg["crawler"].get("concurrent_per_domain", 4)
DEPTH_LIMIT = cfg["crawler"].get("depth_limit", 2)
TELNETCONSOLE_ENABLED = False

ITEM_PIPELINES = {
    "crawler.pipelines.JsonlWriterPipeline": 300,
}

robots_cache = Path(cfg["crawler"]["robots_cache_dir"]).expanduser().resolve()
robots_cache.mkdir(parents=True, exist_ok=True)
ROBOTSTXT_CACHE_ENABLED = True
ROBOTSTXT_CACHE_DIR = str(robots_cache)

log_dir = data_dir(cfg)
log_dir.mkdir(parents=True, exist_ok=True)
LOG_FILE = str((log_dir / "crawler.log").resolve())
LOG_LEVEL = "INFO"

if cfg["crawler"].get("use_js_fallback", False):
    DOWNLOAD_HANDLERS = {
        "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
        "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
    }
    TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
    PLAYWRIGHT_BROWSER_TYPE = "chromium"
