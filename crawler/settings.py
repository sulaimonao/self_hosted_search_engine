"""
Scrapy project settings.

These settings configure the crawler to respect robots.txt, apply a
short delay between requests to the same domain, and write items via
the JsonlWriterPipeline.  Adjust concurrency and delays to suit your
hardware and network limits.
"""

BOT_NAME = "crawler"

SPIDER_MODULES = ["crawler.spiders"]
NEWSPIDER_MODULE = "crawler.spiders"

ROBOTSTXT_OBEY = True

# Throttle requests to avoid overloading hosts.
DOWNLOAD_DELAY = 0.5
CONCURRENT_REQUESTS_PER_DOMAIN = 4

# Enable our pipeline to write out pages.jsonl
ITEM_PIPELINES = {
    "crawler.pipelines.JsonlWriterPipeline": 300,
}

# Cache robots.txt files to reduce overhead on repeated runs
ROBOTSTXT_CACHE_ENABLED = True
ROBOTSTXT_CACHE_DIR = str((__import__("pathlib").Path(__file__).resolve().parents[2] / "data" / "robots_cache").as_posix())

# Uncomment the following lines if you wish to enable Playwright for
# JavaScript rendering.  See README for details.
# DOWNLOAD_HANDLERS = {
#     "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
#     "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
# }
# TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
# PLAYWRIGHT_BROWSER_TYPE = "chromium"