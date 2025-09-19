"""Focused crawler orchestrating HTTP fetching and optional Playwright rendering."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence
from urllib.parse import urljoin, urlparse

try:
    import httpx
except ImportError:  # pragma: no cover - optional dependency
    httpx = None

try:
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover - optional dependency
    BeautifulSoup = None

from backend.app.metrics import metrics
from frontier import ContentFingerprint, RobotsCache, UrlBloom

from .frontier import (
    Candidate,
    CrawlCooldowns,
    DEFAULT_COOLDOWN,
    build_frontier,
    discover_sitemaps,
)

LOGGER = logging.getLogger(__name__)
USER_AGENT = os.getenv("CRAWL_USER_AGENT", "SelfHostedSearchBot/0.2 (+local)")
GLOBAL_CONCURRENCY = int(os.getenv("CRAWL_CONCURRENT_REQUESTS", "8"))
PER_DOMAIN_CONCURRENCY = int(os.getenv("CRAWL_CONCURRENT_PER_DOMAIN", "2"))
MAX_RETRIES = 3
RESPECT_ROBOTS = os.getenv("CRAWL_RESPECT_ROBOTS", "true").lower() not in {"0", "false", "no", "off"}
PLAYWRIGHT_MODE = os.getenv("CRAWL_USE_PLAYWRIGHT", "auto").lower()
PLAYWRIGHT_TIMEOUT = int(os.getenv("PLAYWRIGHT_NAVIGATION_TIMEOUT", "30000"))


@dataclass
class PageResult:
    url: str
    status: int
    html: str
    title: str
    fetched_at: float
    fingerprint: ContentFingerprint
    outlinks: List[str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the focused crawler")
    parser.add_argument("--query", required=True, help="Search query driving the crawl")
    parser.add_argument("--budget", type=int, default=10, help="Maximum pages to fetch")
    parser.add_argument("--out", type=Path, default=Path("data/crawl/raw"))
    parser.add_argument("--use-llm", action="store_true")
    parser.add_argument("--model", help="Optional Ollama model name")
    return parser.parse_args()


async def _maybe_llm_urls(query: str, use_llm: bool, model: Optional[str]) -> List[str]:
    if not use_llm:
        return []
    start = time.perf_counter()
    try:
        from llm.seed_guesser import guess_urls

        urls = guess_urls(query, model=model)
    except Exception as exc:  # pragma: no cover - best effort logging
        LOGGER.warning("LLM seed expansion failed: %s", exc)
        return []
    finally:
        metrics.record_llm_seed_time((time.perf_counter() - start) * 1000)
    return urls


def _extract_title(html: str) -> str:
    start = html.lower().find("<title")
    if start == -1:
        return ""
    end = html.lower().find("</title>", start)
    if end == -1:
        return ""
    segment = html[start:end]
    closing = segment.find(">")
    if closing == -1:
        return ""
    return segment[closing + 1 :].strip()


def _visible_text_length(html: str) -> int:
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml")
        for element in soup.select("script, style, noscript"):
            element.decompose()
        return len(soup.get_text(" ", strip=True))
    except Exception:
        return len(html)


async def _fetch_with_playwright(url: str) -> Optional[PageResult]:
    try:
        from playwright.async_api import async_playwright
    except Exception as exc:  # pragma: no cover - optional dependency issues
        LOGGER.warning("Playwright unavailable: %s", exc)
        return None

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            response = await page.goto(url, wait_until="networkidle", timeout=PLAYWRIGHT_TIMEOUT)
            html = await page.content()
            title = await page.title()
            status = response.status if response else 200
            fingerprint = ContentFingerprint.from_text(html)
            outlinks = _extract_outlinks(url, html)
            await browser.close()
            metrics.record_playwright_use()
            return PageResult(
                url=url,
                status=status,
                html=html,
                title=title,
                fetched_at=time.time(),
                fingerprint=fingerprint,
                outlinks=outlinks,
            )
    except Exception as exc:
        LOGGER.debug("Playwright fetch failed for %s: %s", url, exc)
        return None


def _should_use_playwright(html: str) -> bool:
    if PLAYWRIGHT_MODE in {"0", "false", "no", "off"}:
        return False
    if PLAYWRIGHT_MODE in {"1", "true", "yes", "on"}:
        return True
    visible_len = _visible_text_length(html)
    if visible_len >= 1500:
        return False
    lowered = html.lower()
    hints = ["#/", "data-reactroot", "ng-app", "id=\"app\"", "window.__INITIAL_STATE__", "<app-root"]
    return any(hint in lowered for hint in hints)


def _extract_outlinks(base_url: str, html: str, limit: int = 100) -> List[str]:
    links: List[str] = []
    if BeautifulSoup:
        soup = BeautifulSoup(html, "lxml")
        for element in soup.find_all("a"):
            href = element.get("href")
            if not href:
                continue
            candidate = urljoin(base_url, href)
            links.append(candidate)
            if len(links) >= limit:
                break
    else:
        for match in re.finditer(r"href=\"([^\"]+)\"", html, flags=re.IGNORECASE):
            href = match.group(1)
            if not href:
                continue
            links.append(urljoin(base_url, href))
            if len(links) >= limit:
                break
    return links


class FocusedCrawler:
    def __init__(
        self,
        query: str,
        budget: int,
        out_dir: Path,
        use_llm: bool,
        model: Optional[str],
        initial_seeds: Optional[Sequence[Candidate]] = None,
    ) -> None:
        self.query = query
        self.budget = max(1, budget)
        self.out_dir = out_dir
        self.use_llm = use_llm
        self.model = model
        self.initial_seeds = list(initial_seeds) if initial_seeds else None
        self.cooldowns = CrawlCooldowns(out_dir.parent / "cooldowns.json")
        self.results: List[PageResult] = []
        self.visited: set[str] = set()
        self.robots = RobotsCache(respect=RESPECT_ROBOTS, user_agent=USER_AGENT)
        self._url_filter = UrlBloom(capacity=max(1024, budget * 10))
        self._content_seen: set[str] = set()
        self._domain_locks: Dict[str, asyncio.Semaphore] = {}
        self._domain_lock_guard: Optional[asyncio.Lock] = None
        self._results_lock: Optional[asyncio.Lock] = None
        self.last_output_path: Optional[Path] = None
        if not RESPECT_ROBOTS:
            LOGGER.warning("Robots.txt enforcement disabled for this run")

    async def run(self) -> None:
        if httpx is None:
            raise RuntimeError("httpx is required to run the focused crawler")
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self._domain_lock_guard = asyncio.Lock()
        self._results_lock = asyncio.Lock()
        async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}) as client:
            if self.initial_seeds is not None:
                seeds = list(self.initial_seeds)
            else:
                extra_urls = await _maybe_llm_urls(self.query, self.use_llm, self.model)
                frontier = build_frontier(
                    self.query,
                    extra_urls=extra_urls,
                    budget=self.budget * 4,
                    cooldowns=self.cooldowns,
                    cooldown_seconds=DEFAULT_COOLDOWN,
                )
                seeds = await self._expand_with_sitemaps(client, frontier)
            await self._crawl(client, seeds)
        self.cooldowns.save()
        self._persist_results()

    async def _expand_with_sitemaps(self, client: httpx.AsyncClient, seeds: List[Candidate]) -> List[Candidate]:
        enriched: List[Candidate] = []
        for candidate in seeds:
            enriched.append(candidate)
            if len(enriched) >= self.budget * 2:
                continue
            sitemap_urls = await discover_sitemaps(client, candidate.url, limit=5)
            for url in sitemap_urls:
                enriched.append(Candidate(url=url, source="sitemap", weight=candidate.weight * 0.8))
        return enriched

    async def _crawl(self, client: httpx.AsyncClient, seeds: List[Candidate]) -> None:
        queue: asyncio.Queue[Candidate] = asyncio.Queue()
        for candidate in seeds:
            await queue.put(candidate)
        stop_event = asyncio.Event()
        workers = [asyncio.create_task(self._worker(client, queue, stop_event)) for _ in range(GLOBAL_CONCURRENCY)]
        await queue.join()
        stop_event.set()
        for _ in workers:
            await queue.put(Candidate(url="", source="stop", weight=0))
        await asyncio.gather(*workers, return_exceptions=True)

    async def _worker(
        self,
        client: httpx.AsyncClient,
        queue: asyncio.Queue[Candidate],
        stop_event: asyncio.Event,
    ) -> None:
        while True:
            candidate = await queue.get()
            if not candidate.url:
                queue.task_done()
                break
            if stop_event.is_set():
                queue.task_done()
                continue
            url = candidate.url
            if url in self._url_filter:
                queue.task_done()
                continue
            self._url_filter.add(url)
            if url in self.visited:
                queue.task_done()
                continue
            domain = urlparse(url).netloc.lower()
            lock = await self._get_domain_lock(domain)
            async with lock:
                result = await self._fetch_single(client, candidate)
            queue.task_done()
            if result:
                assert self._results_lock is not None
                async with self._results_lock:
                    if len(self.results) >= self.budget:
                        stop_event.set()
                        continue
                    self.results.append(result)
                    self.visited.add(url)
                    self.cooldowns.mark(self.query, domain, time.time())
                    if len(self.results) >= self.budget:
                        stop_event.set()

    async def _get_domain_lock(self, domain: str) -> asyncio.Semaphore:
        if self._domain_lock_guard is None:
            raise RuntimeError("domain lock guard not initialized")
        async with self._domain_lock_guard:
            lock = self._domain_locks.get(domain)
            if lock is None:
                lock = asyncio.Semaphore(PER_DOMAIN_CONCURRENCY)
                self._domain_locks[domain] = lock
            return lock

    async def _fetch_single(self, client: httpx.AsyncClient, candidate: Candidate) -> Optional[PageResult]:
        url = candidate.url
        if url in self.visited:
            return None
        if RESPECT_ROBOTS and not await self.robots.allowed_async(client, url):
            LOGGER.debug("blocked by robots: %s", url)
            return None
        if PLAYWRIGHT_MODE in {"1", "true", "yes", "on"}:
            replacement = await _fetch_with_playwright(url)
            if replacement:
                fingerprint = replacement.fingerprint
                if fingerprint.md5 in self._content_seen:
                    return None
                self._content_seen.add(fingerprint.md5)
                metrics.record_crawl_pages(1)
                return replacement
        backoff = 1.0
        last_error: Optional[Exception] = None
        for _ in range(MAX_RETRIES):
            try:
                response = await client.get(url, timeout=10.0, follow_redirects=True)
                status = response.status_code
                html = response.text
                title = _extract_title(html)
                fingerprint = ContentFingerprint.from_text(html)
                if fingerprint.md5 in self._content_seen:
                    return None
                metrics.record_crawl_pages(1)
                if PLAYWRIGHT_MODE != "0" and _should_use_playwright(html):
                    replacement = await _fetch_with_playwright(str(response.url))
                    if replacement:
                        fingerprint = replacement.fingerprint
                        if fingerprint.md5 in self._content_seen:
                            return None
                        self._content_seen.add(fingerprint.md5)
                        return replacement
                outlinks = _extract_outlinks(str(response.url), html)
                self._content_seen.add(fingerprint.md5)
                return PageResult(
                    url=str(response.url),
                    status=status,
                    html=html,
                    title=title,
                    fetched_at=time.time(),
                    fingerprint=fingerprint,
                    outlinks=outlinks,
                )
            except Exception as exc:
                last_error = exc
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 8.0)
        if last_error:
            LOGGER.debug("failed to fetch %s: %s", url, last_error)
        return None

    def _persist_results(self) -> None:
        if not self.results:
            LOGGER.info("No pages fetched for query '%s'", self.query)
            self.last_output_path = None
            return
        timestamp = int(time.time())
        path = self.out_dir / f"focused_{timestamp}.jsonl"
        with path.open("w", encoding="utf-8") as handle:
            for result in self.results:
                    handle.write(
                        json.dumps(
                            {
                                "query": self.query,
                                "url": result.url,
                                "status": result.status,
                                "title": result.title,
                                "html": result.html,
                                "fetched_at": result.fetched_at,
                                "content_hash": result.fingerprint.md5,
                                "simhash": result.fingerprint.simhash,
                                "outlinks": result.outlinks,
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                )
        LOGGER.info("Persisted %s page(s) to %s", len(self.results), path)
        self.last_output_path = path


async def async_main(args: argparse.Namespace) -> None:
    crawler = FocusedCrawler(
        query=args.query,
        budget=args.budget,
        out_dir=args.out,
        use_llm=args.use_llm,
        model=args.model,
    )
    await crawler.run()


def main() -> None:
    logging.basicConfig(level=os.getenv("CRAWL_LOG_LEVEL", "INFO"))
    args = parse_args()
    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
