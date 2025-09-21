"""Polite web crawler used for cold-start indexing."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Optional

import requests
import trafilatura
from bs4 import BeautifulSoup


@dataclass(slots=True)
class CrawlResult:
    url: str
    status_code: int
    html: str
    text: str
    title: str
    etag: str | None
    last_modified: str | None
    content_hash: str


class CrawlError(RuntimeError):
    """Raised when the crawler encounters an unrecoverable error."""


class CrawlClient:
    """Fetches pages while being respectful with delays and timeouts."""

    def __init__(
        self,
        user_agent: str,
        request_timeout: float = 15.0,
        read_timeout: float = 30.0,
        min_delay: float = 1.0,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.user_agent = user_agent
        self.request_timeout = request_timeout
        self.read_timeout = read_timeout
        self.min_delay = min_delay
        self._session = session or requests.Session()
        self._last_fetch = 0.0

    def _throttle(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_fetch
        if elapsed < self.min_delay:
            time.sleep(self.min_delay - elapsed)
        self._last_fetch = time.monotonic()

    def fetch(self, url: str) -> CrawlResult | None:
        self._throttle()
        try:
            response = self._session.get(
                url,
                headers={"User-Agent": self.user_agent},
                timeout=(self.request_timeout, self.read_timeout),
            )
        except requests.RequestException as exc:  # pragma: no cover - network failure
            raise CrawlError(str(exc)) from exc
        if response.status_code >= 400:
            return None
        html = response.text
        text = self._extract_text(html)
        if not text.strip():
            return None
        title = self._extract_title(html)
        etag = response.headers.get("ETag")
        last_modified = response.headers.get("Last-Modified")
        content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return CrawlResult(
            url=url,
            status_code=response.status_code,
            html=html,
            text=text,
            title=title,
            etag=etag,
            last_modified=last_modified,
            content_hash=content_hash,
        )

    @staticmethod
    def _extract_text(html: str) -> str:
        extracted = trafilatura.extract(html, include_comments=False, favour_precision=True)
        if extracted:
            return extracted
        soup = BeautifulSoup(html, "html.parser")
        for script in soup(["script", "style"]):
            script.extract()
        return "\n".join(segment.strip() for segment in soup.get_text().splitlines() if segment.strip())

    @staticmethod
    def _extract_title(html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        title_tag = soup.find("title")
        if title_tag and title_tag.text:
            return title_tag.text.strip()
        return ""


__all__ = ["CrawlClient", "CrawlResult", "CrawlError"]
