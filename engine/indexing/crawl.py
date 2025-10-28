"""Polite web crawler used for cold-start indexing."""

from __future__ import annotations

import atexit
import hashlib
import logging
import threading
import time
from dataclasses import dataclass
from typing import Optional, Callable

import requests
import trafilatura
from bs4 import BeautifulSoup

try:  # Optional dependency – degrade gracefully when Playwright is missing
    from playwright.sync_api import (
        Error as PlaywrightError,
        TimeoutError as PlaywrightTimeout,
        sync_playwright,
    )
except Exception:  # pragma: no cover - optional dependency guard
    PlaywrightError = PlaywrightTimeout = RuntimeError
    sync_playwright = None


LOGGER = logging.getLogger(__name__)


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
        *,
        enable_browser_fallback: bool = True,
        browser_type: str = "chromium",
        browser_headless: bool = True,
        browser_navigation_timeout: int = 30_000,
        browser_wait_after_load: float = 0.5,
        clearance_callback: Optional[Callable[[requests.Response, str | None], None]] = None,
    ) -> None:
        self.user_agent = user_agent
        self.request_timeout = request_timeout
        self.read_timeout = read_timeout
        self.min_delay = min_delay
        self._session = session
        self._session_lock = threading.Lock()
        self._last_fetch = 0.0
        self._throttle_lock = threading.Lock()
        if self._session is None:
            self._session = self._build_session()
        else:
            self._session.headers.update(self._default_headers())
        self._browser_enabled = bool(enable_browser_fallback) and sync_playwright is not None
        self._browser_type = (browser_type or "chromium").lower()
        self._browser_headless = bool(browser_headless)
        self._browser_navigation_timeout = int(browser_navigation_timeout)
        self._browser_wait_after_load = max(0.0, float(browser_wait_after_load))
        self._browser_lock = threading.Lock()
        self._playwright = None
        self._browser = None
        self._clearance_callback = clearance_callback
        if self._browser_enabled:
            atexit.register(self.close)

    def _throttle(self) -> None:
        with self._throttle_lock:
            now = time.monotonic()
            wait_time = self.min_delay - (now - self._last_fetch)
            if wait_time > 0:
                time.sleep(wait_time)
                now = time.monotonic()
            self._last_fetch = now

    def fetch(self, url: str) -> CrawlResult | None:
        self._throttle()
        request_exc: requests.RequestException | None = None
        result: CrawlResult | None = None
        try:
            with self._session_lock:
                session = self._session
                if session is None:
                    session = self._build_session()
                    self._session = session
                response = session.get(
                    url,
                    timeout=(self.request_timeout, self.read_timeout),
                    allow_redirects=True,
                )
        except requests.RequestException as exc:  # pragma: no cover - network failure
            LOGGER.debug("requests fetch failed for url=%s: %s", url, exc)
            response = None
            request_exc = exc
        if response is not None:
            result = self._build_result_from_response(response)
            self._record_clearance(response, getattr(response, "text", ""))
            if self._should_skip_browser(response, result):
                return result
        if not self._browser_enabled:
            if result is not None:
                return result
            if request_exc is not None:
                raise CrawlError(str(request_exc)) from request_exc
            return None
        browser_result = self._fetch_with_browser(url)
        if browser_result is not None:
            # Prefer browser result when we fetched via browser or when it extracts more text.
            if result is None or len(browser_result.text) > len(result.text):
                self._record_clearance(response, getattr(response, "text", "") if response else browser_result.html)
                return browser_result
        if result is not None:
            if response is not None:
                self._record_clearance(response, getattr(response, "text", ""))
            return result
        if request_exc is not None:
            raise CrawlError(str(request_exc)) from request_exc
        return None

    def _record_clearance(self, response: requests.Response | None, html: str | None) -> None:
        callback = self._clearance_callback
        if callback is None or response is None:
            return
        try:
            callback(response, html)
        except Exception:  # pragma: no cover - detection is best effort
            LOGGER.debug("clearance callback failed", exc_info=True)

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

    def close(self) -> None:
        with self._browser_lock:
            browser = self._browser
            playwright = self._playwright
            self._browser = None
            self._playwright = None
        if browser is not None:
            try:
                browser.close()
            except Exception:  # pragma: no cover - best effort cleanup
                pass
        if playwright is not None:
            try:
                playwright.stop()
            except Exception:  # pragma: no cover - best effort cleanup
                pass
        with self._session_lock:
            session = self._session
            self._session = None
        if session is not None:
            try:
                session.close()
            except Exception:  # pragma: no cover - best effort cleanup
                pass

    def _default_headers(self) -> dict[str, str]:
        return {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
        }

    def _build_session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update(self._default_headers())
        return session

    def _build_result_from_response(self, response: requests.Response) -> CrawlResult | None:
        status = response.status_code
        if status >= 400:
            return None
        html = response.text or ""
        text = self._extract_text(html)
        if not text.strip():
            return CrawlResult(
                url=response.url,
                status_code=status,
                html=html,
                text="",
                title=self._extract_title(html),
                etag=response.headers.get("ETag"),
                last_modified=response.headers.get("Last-Modified"),
                content_hash="",
            )
        title = self._extract_title(html)
        etag = response.headers.get("ETag")
        last_modified = response.headers.get("Last-Modified")
        content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return CrawlResult(
            url=response.url,
            status_code=status,
            html=html,
            text=text,
            title=title,
            etag=etag,
            last_modified=last_modified,
            content_hash=content_hash,
        )

    def _should_skip_browser(
        self, response: requests.Response, result: CrawlResult | None
    ) -> bool:
        if not self._browser_enabled:
            return True
        if response.status_code >= 400:
            return False
        if result is None:
            return False
        if not result.text.strip():
            return False
        content_type = response.headers.get("Content-Type", "").lower()
        if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
            return True
        # Fallback when page likely rendered via client-side JS (very small text extracts)
        if len(result.text) < 500:
            return False
        return True

    def _ensure_browser(self):
        if not self._browser_enabled:
            return None
        with self._browser_lock:
            if self._browser is not None:
                return self._browser
            try:
                playwright = sync_playwright().start()
                browser_factory = getattr(playwright, self._browser_type, None)
                if browser_factory is None:
                    LOGGER.debug(
                        "Unknown browser type '%s'; defaulting to chromium",
                        self._browser_type,
                    )
                    browser_factory = playwright.chromium
                browser = browser_factory.launch(headless=self._browser_headless)
            except Exception as exc:  # pragma: no cover - optional dependency failure
                LOGGER.debug("Failed to start Playwright browser: %s", exc)
                self._browser_enabled = False
                return None
            self._playwright = playwright
            self._browser = browser
            return browser

    def _fetch_with_browser(self, url: str) -> CrawlResult | None:
        browser = self._ensure_browser()
        if browser is None:
            return None
        with self._browser_lock:
            context = browser.new_context(ignore_https_errors=True, user_agent=self.user_agent)
            try:
                page = context.new_page()
                response = page.goto(
                    url,
                    wait_until="load",
                    timeout=self._browser_navigation_timeout,
                )
                if self._browser_wait_after_load:
                    time.sleep(self._browser_wait_after_load)
                html = page.content()
                text = self._extract_text(html)
                if not text.strip():
                    return None
                title = self._extract_title(html)
                status_code = response.status if response is not None else 200
                headers = response.headers if response is not None else {}
                etag = headers.get("etag") if headers else None
                last_modified = headers.get("last-modified") if headers else None
                content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
                return CrawlResult(
                    url=page.url,
                    status_code=status_code,
                    html=html,
                    text=text,
                    title=title,
                    etag=etag,
                    last_modified=last_modified,
                    content_hash=content_hash,
                )
            except (PlaywrightTimeout, PlaywrightError) as exc:  # pragma: no cover - browser failure
                LOGGER.debug("Browser fetch failed for url=%s: %s", url, exc)
            except Exception as exc:  # pragma: no cover - defensive
                LOGGER.debug("Unexpected browser error for url=%s", url, exc_info=True)
            finally:
                try:
                    context.close()
                except Exception:  # pragma: no cover - best effort cleanup
                    pass
        return None

    def __del__(self):  # pragma: no cover - destructor safety
        try:
            self.close()
        except Exception:
            pass


__all__ = ["CrawlClient", "CrawlResult", "CrawlError"]
