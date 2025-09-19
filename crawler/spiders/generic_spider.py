"""Generic breadth-first crawler for the self-hosted search engine."""

from __future__ import annotations

import re
import time
from typing import Iterable, Sequence
from urllib.parse import urlparse

import scrapy


def _clean_text(text_parts: Sequence[str]) -> str:
    cleaned = " ".join(part.strip() for part in text_parts if part and part.strip())
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


class GenericSpider(scrapy.Spider):
    name = "generic"

    custom_settings = {
        "PLAYWRIGHT_PROCESS_REQUEST_HEADERS": None,
    }

    def __init__(
        self,
        seeds: Iterable[str],
        crawl_store: str,
        max_pages: int = 200,
        allow_list: Sequence[str] | None = None,
        deny_list: Sequence[str] | None = None,
        use_playwright: bool = False,
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.start_urls = [s for s in seeds if s]
        self.max_pages = max(1, int(max_pages))
        self.pages_seen = 0
        self.allow_list = [p for p in (allow_list or []) if p]
        self.deny_list = [p for p in (deny_list or []) if p]
        self.use_playwright = use_playwright
        self.crawl_store = crawl_store
        domains = {urlparse(url).netloc for url in self.start_urls if urlparse(url).netloc}
        self.allowed_domains = sorted(domains)

    def _should_visit(self, url: str) -> bool:
        lowered = url.lower()
        if self.allow_list and not any(pattern.lower() in lowered for pattern in self.allow_list):
            return False
        if any(pattern.lower() in lowered for pattern in self.deny_list):
            return False
        return True

    def _request_kwargs(self):
        if self.use_playwright:
            return {"meta": {"playwright": True}}
        return {}

    def start_requests(self):
        if not self.start_urls:
            raise RuntimeError("No seeds provided to GenericSpider")
        for url in self.start_urls:
            yield scrapy.Request(url=url, callback=self.parse, dont_filter=True, **self._request_kwargs())

    def parse(self, response: scrapy.http.Response):
        if self.pages_seen >= self.max_pages:
            return
        self.pages_seen += 1

        title = response.xpath("//title/text()").get() or response.xpath("//h1/text()").get() or ""
        text_nodes = response.xpath("//body//text()[normalize-space()]").getall()
        text = _clean_text(text_nodes)
        canonical = response.css("link[rel=canonical]::attr(href)").get()
        if canonical:
            canonical = response.urljoin(canonical)
        lang = response.xpath("//html/@lang").get() or response.css("meta[http-equiv='content-language']::attr(content)").get()
        outlinks: list[str] = []
        for href in response.css("a::attr(href)").getall():
            if not href:
                continue
            next_url = response.urljoin(href)
            if next_url not in outlinks:
                outlinks.append(next_url)
            if not self._should_visit(next_url):
                continue
            yield response.follow(next_url, callback=self.parse, **self._request_kwargs())

        yield {
            "url": response.url,
            "status": response.status,
            "title": title.strip(),
            "text": text,
            "raw_html": response.text,
            "canonical_url": canonical,
            "lang": (lang or "").split(",")[0].strip() if lang else "",
            "outlinks": outlinks[:100],
            "fetched_at": time.time(),
        }
        if self.pages_seen >= self.max_pages:
            return
