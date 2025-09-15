import re
from urllib.parse import urljoin
import scrapy
from w3lib.html import remove_tags
from crawler.items import PageItem

class SiteSpider(scrapy.Spider):
    """
    General purpose spider that crawls pages starting from one or more
    seed URLs.  It follows links within the allowed domains and
    extracts the page title, raw HTML, and cleaned text.  Use this
    spider when you want to explore a specific website or a small set
    of sites in depth.
    """
    name = "site"

    custom_settings = {
        "DEPTH_PRIORITY": 1,
        "SCHEDULER_DISK_QUEUE": "scrapy.squeues.PickleFifoDiskQueue",
        "SCHEDULER_MEMORY_QUEUE": "scrapy.squeues.FifoMemoryQueue",
        "LOG_LEVEL": "INFO",
    }

    def __init__(self, start_urls="", allow="", deny="", max_pages=1000, *args, **kwargs):
        """
        :param start_urls: comma-separated list of seed URLs.
        :param allow: regular expression; only follow links matching this.
        :param deny: regular expression; do not follow links matching this.
        :param max_pages: maximum number of pages to crawl before stopping.
        """
        super().__init__(*args, **kwargs)
        self.start_urls = [u.strip() for u in start_urls.split(",") if u.strip()]
        self.allow_pattern = re.compile(allow) if allow else None
        self.deny_pattern = re.compile(deny) if deny else None
        self.max_pages = int(max_pages)
        self.pages_crawled = 0
        self.seen = set()

    def parse(self, response):
        if self.pages_crawled >= self.max_pages:
            return

        # Mark this URL as seen
        url = response.url
        if url in self.seen:
            return
        self.seen.add(url)

        # Extract the page title and body text
        title = response.xpath("//title/text()").get(default="").strip()
        body_html = response.xpath("//body").get(default="")
        text = remove_tags(body_html).strip()

        # Yield the item
        self.pages_crawled += 1
        yield PageItem(url=url, title=title, html=body_html, text=text)

        # Follow links, breadth-first
        if self.pages_crawled >= self.max_pages:
            return

        for href in response.css("a::attr(href)").getall():
            # Remove fragment identifiers
            next_url = urljoin(response.url, href.split("#")[0])
            # Deduplicate
            if next_url in self.seen:
                continue
            # Apply allow/deny patterns
            if self.deny_pattern and self.deny_pattern.search(next_url):
                continue
            if self.allow_pattern and not self.allow_pattern.search(next_url):
                continue
            # Skip mailto: and javascript: links
            if next_url.startswith("mailto:") or next_url.startswith("javascript:"):
                continue
            yield scrapy.Request(next_url, callback=self.parse)