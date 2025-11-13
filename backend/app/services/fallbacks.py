"""Site discovery helpers providing layered browsing fallbacks."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlparse, quote

import requests
from bs4 import BeautifulSoup


LOGGER = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": "SelfHostedSearch/1.0 (+https://github.com/sulaimonao/self_hosted_search_engine)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

FEED_PATHS = (
    "/feed",
    "/rss",
    "/rss.xml",
    "/atom.xml",
    "/index.xml",
)

SEARCH_TEMPLATES = (
    "/search?q={query}",
    "/?s={query}",
    "/search/{query}",
)

MAX_ITEMS = 50


@dataclass(slots=True)
class FallbackResult:
    strategy: str
    url: str
    title: str | None
    items: list[dict[str, Any]]
    diagnostics: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "url": self.url,
            "title": self.title,
            "items": self.items,
            "diagnostics": self.diagnostics,
        }


class SmartFetcher:
    """Lightweight helper executing layered fetch strategies."""

    def __init__(self, *, timeout: float = 12.0) -> None:
        self._timeout = timeout

    # ------------------------------------------------------------------
    def smart_fetch(self, url: str, query: str | None = None) -> FallbackResult:
        normalized = self._normalize_url(url)
        diagnostics: list[str] = []
        if not normalized:
            return FallbackResult("none", url, None, [], ["invalid_url"])

        strategies = (
            lambda: self._discover_feed(normalized, diagnostics),
            lambda: self._site_search(normalized, query, diagnostics),
            lambda: self._homepage_scrape(normalized, diagnostics),
        )
        for strategy in strategies:
            result = strategy()
            if result is not None and result.items:
                return result
        return FallbackResult(
            "none", normalized, None, [], diagnostics or ["no_results"]
        )

    # ------------------------------------------------------------------
    def _request(self, url: str) -> requests.Response | None:
        try:
            resp = requests.get(
                url,
                headers=DEFAULT_HEADERS,
                timeout=self._timeout,
                allow_redirects=True,
            )
        except requests.RequestException:
            LOGGER.debug("smart fetch HTTP error", exc_info=True)
            return None
        if resp.status_code >= 400:
            return None
        return resp

    def _discover_feed(self, url: str, diagnostics: list[str]) -> FallbackResult | None:
        for path in FEED_PATHS:
            candidate = urljoin(url, path)
            resp = self._request(candidate)
            if resp is None:
                continue
            if self._looks_like_feed(resp.text):
                items = self._extract_feed_items(resp.text)
                if items:
                    return FallbackResult(
                        "rss",
                        candidate,
                        self._page_title(resp.text),
                        items,
                        diagnostics,
                    )
        # check <link rel="alternate">
        resp = self._request(url)
        if resp is None:
            diagnostics.append("feed_root_request_failed")
            return None
        soup = BeautifulSoup(resp.text, "html.parser")
        for link in soup.select("link[rel='alternate']"):
            link_type = (link.get("type") or "").lower()
            if "rss" not in link_type and "atom" not in link_type:
                continue
            href = link.get("href")
            if not href:
                continue
            feed_url = urljoin(resp.url, href)
            feed_resp = self._request(feed_url)
            if feed_resp is None:
                continue
            if self._looks_like_feed(feed_resp.text):
                items = self._extract_feed_items(feed_resp.text)
                if items:
                    return FallbackResult(
                        "rss",
                        feed_url,
                        self._page_title(feed_resp.text),
                        items,
                        diagnostics,
                    )
        diagnostics.append("feed_not_found")
        return None

    def _site_search(
        self, url: str, query: str | None, diagnostics: list[str]
    ) -> FallbackResult | None:
        if not query:
            diagnostics.append("no_query_for_search")
            return None
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        encoded = quote(query)
        for template in SEARCH_TEMPLATES:
            candidate = urljoin(base, template.format(query=encoded))
            resp = self._request(candidate)
            if resp is None or not (resp.text or "").strip():
                continue
            items = self._extract_links(resp.text, base)
            if items:
                return FallbackResult(
                    "site_search",
                    candidate,
                    self._page_title(resp.text),
                    items,
                    diagnostics,
                )
        diagnostics.append("site_search_empty")
        return None

    def _homepage_scrape(
        self, url: str, diagnostics: list[str]
    ) -> FallbackResult | None:
        resp = self._request(url)
        if resp is None:
            diagnostics.append("homepage_fetch_failed")
            return None
        items = self._extract_links(resp.text, resp.url)
        return FallbackResult(
            "homepage",
            resp.url,
            self._page_title(resp.text),
            items,
            diagnostics,
        )

    # ------------------------------------------------------------------
    @staticmethod
    def _normalize_url(url: str) -> str | None:
        text = (url or "").strip()
        if not text:
            return None
        parsed = urlparse(text if "://" in text else f"https://{text}")
        if not parsed.scheme or not parsed.netloc:
            return None
        scheme = parsed.scheme.lower()
        if scheme not in {"http", "https"}:
            return None
        normalized = f"{scheme}://{parsed.netloc}{parsed.path or '/'}"
        if parsed.query:
            normalized += f"?{parsed.query}"
        return normalized.rstrip("/")

    @staticmethod
    def _looks_like_feed(text: str) -> bool:
        lowered = text.lower()
        return "<rss" in lowered or "<feed" in lowered

    @staticmethod
    def _page_title(html: str) -> str | None:
        soup = BeautifulSoup(html, "html.parser")
        title = soup.find("title")
        if title and title.text:
            return title.text.strip()
        return None

    @staticmethod
    def _extract_feed_items(xml_text: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        pattern = re.compile(
            r"<item[\s\S]*?<title>(?P<title>[^<]+)</title>[\s\S]*?<link>(?P<link>[^<]+)</link>",
            re.I,
        )
        for match in pattern.finditer(xml_text or ""):
            title = match.group("title").strip()
            link = match.group("link").strip()
            if not title or not link:
                continue
            items.append({"title": title, "url": link})
            if len(items) >= MAX_ITEMS:
                break
        return items

    @staticmethod
    def _extract_links(html: str, base_url: str) -> list[dict[str, Any]]:
        soup = BeautifulSoup(html, "html.parser")
        articles = SmartFetcher._extract_structured_links(soup, base_url)
        if articles:
            return articles
        discovered: list[dict[str, Any]] = []
        for anchor in soup.select("a[href]"):
            href = anchor.get("href")
            if not href or href.startswith("#"):
                continue
            text = (anchor.get_text() or "").strip()
            if not text:
                continue
            absolute = urljoin(base_url, href)
            discovered.append({"title": text[:200], "url": absolute})
            if len(discovered) >= MAX_ITEMS:
                break
        return discovered

    @staticmethod
    def _extract_structured_links(
        soup: BeautifulSoup, base_url: str
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        # JSON-LD articles
        for script in soup.select("script[type='application/ld+json']"):
            try:
                data = script.string or ""
                payload = json.loads(data)
            except Exception:
                continue
            SmartFetcher._collect_ld_items(payload, base_url, items)
            if len(items) >= MAX_ITEMS:
                return items
        # Article and nav anchors with data-headline or aria-current
        for selector in ("article a", "nav a", "main a"):
            for anchor in soup.select(selector):
                href = anchor.get("href")
                if not href or href.startswith("#"):
                    continue
                text = (anchor.get_text() or "").strip()
                if not text:
                    continue
                absolute = urljoin(base_url, href)
                items.append({"title": text[:200], "url": absolute})
                if len(items) >= MAX_ITEMS:
                    return items
        return items

    @staticmethod
    def _collect_ld_items(
        payload: Any, base_url: str, items: list[dict[str, Any]]
    ) -> None:
        if isinstance(payload, list):
            for entry in payload:
                SmartFetcher._collect_ld_items(entry, base_url, items)
            return
        if not isinstance(payload, dict):
            return
        type_val = str(payload.get("@type") or "")
        if type_val.lower() in {"article", "newsarticle", "blogposting"}:
            url = payload.get("url") or payload.get("@id")
            headline = payload.get("headline") or payload.get("name")
            if isinstance(url, str) and isinstance(headline, str):
                absolute = urljoin(base_url, url)
                items.append({"title": headline[:200], "url": absolute})
                return
        for value in payload.values():
            SmartFetcher._collect_ld_items(value, base_url, items)


def smart_fetch(url: str, query: str | None = None) -> dict[str, Any]:
    fetcher = SmartFetcher()
    result = fetcher.smart_fetch(url, query=query)
    return result.to_dict()


__all__ = ["smart_fetch", "SmartFetcher", "FallbackResult"]
