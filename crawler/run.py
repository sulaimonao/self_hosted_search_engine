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
from typing import Callable, Dict, Iterable, List, Optional, Sequence
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
from backend.app.services.source_follow import (
    BudgetExceeded,
    SourceBudget,
    SourceFollowConfig,
    SourceLink,
    extract_sources,
)
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
    sources: List[SourceLink]
    is_source: bool
    parent_url: Optional[str]


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


async def _fetch_with_playwright(url: str, candidate: Optional[Candidate] = None) -> Optional[PageResult]:
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
            sources = extract_sources(html, url)
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
                sources=sources,
                is_source=candidate.is_source if candidate else False,
                parent_url=candidate.parent_url if candidate else None,
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
        source_config: Optional[SourceFollowConfig] = None,
        record_source_links: Optional[Callable[[str, Sequence[SourceLink], bool], None]] = None,
        record_missing_source: Optional[
            Callable[[str, str, str, Optional[int], Optional[str], Optional[str]], None]
        ] = None,
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
        self._queued_urls: set[str] = set()
        self.source_config = source_config or SourceFollowConfig()
        self.source_budget = SourceBudget(self.source_config) if self.source_config.enabled else None
        self._record_source_links = record_source_links
        self._record_missing_source = record_missing_source
        self.source_stats = {
            "discovered": 0,
            "enqueued": 0,
            "skipped": 0,
            "budget_exhausted": False,
        }
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
                base = candidate.score if candidate.score is not None else candidate.weight
                enriched.append(
                    Candidate(
                        url=url,
                        source="sitemap",
                        weight=candidate.weight * 0.8,
                        score=base * 0.8,
                    )
                )
        return enriched

    async def _crawl(self, client: httpx.AsyncClient, seeds: List[Candidate]) -> None:
        queue: asyncio.Queue[Candidate] = asyncio.Queue()
        for candidate in seeds:
            await queue.put(candidate)
            self._queued_urls.add(candidate.url)
        stop_event = asyncio.Event()
        workers = [asyncio.create_task(self._worker(client, queue, stop_event)) for _ in range(GLOBAL_CONCURRENCY)]
        await queue.join()
        stop_event.set()
        for _ in workers:
            await queue.put(Candidate(url="", source="stop", weight=0, score=0.0))
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
                result, failure = await self._fetch_single(client, candidate)
            queue.task_done()
            if result:
                assert self._results_lock is not None
                follow_sources = bool(self.source_budget)
                pending_sources = result.sources if self.source_budget else []
                async with self._results_lock:
                    if len(self.results) >= self.budget:
                        stop_event.set()
                        continue
                    self.results.append(result)
                    self.visited.add(url)
                    self.cooldowns.mark(self.query, domain, time.time())
                    if pending_sources:
                        self.source_stats["discovered"] += len(pending_sources)
                    if len(self.results) >= self.budget:
                        stop_event.set()
                if follow_sources:
                    await self._handle_sources(candidate, result, queue)
            elif failure and candidate.is_source:
                self._handle_source_failure(candidate, failure)

    async def _get_domain_lock(self, domain: str) -> asyncio.Semaphore:
        if self._domain_lock_guard is None:
            raise RuntimeError("domain lock guard not initialized")
        async with self._domain_lock_guard:
            lock = self._domain_locks.get(domain)
            if lock is None:
                lock = asyncio.Semaphore(PER_DOMAIN_CONCURRENCY)
                self._domain_locks[domain] = lock
            return lock

    async def _fetch_single(
        self, client: httpx.AsyncClient, candidate: Candidate
    ) -> tuple[Optional[PageResult], Optional[dict[str, object]]]:
        url = candidate.url
        if url in self.visited:
            return None, None
        if RESPECT_ROBOTS and not await self.robots.allowed_async(client, url):
            LOGGER.debug("blocked by robots: %s", url)
            return None, {"reason": "robots", "next_action": "manual"}
        if PLAYWRIGHT_MODE in {"1", "true", "yes", "on"}:
            replacement = await _fetch_with_playwright(url, candidate)
            if replacement:
                fingerprint = replacement.fingerprint
                if fingerprint.md5 in self._content_seen:
                    return None, None
                self._content_seen.add(fingerprint.md5)
                metrics.record_crawl_pages(1)
                return replacement, None
        backoff = 1.0
        last_failure: Optional[dict[str, object]] = None
        for _ in range(MAX_RETRIES):
            try:
                response = await client.get(url, timeout=10.0, follow_redirects=True)
                status = response.status_code
                html = response.text
                title = _extract_title(html)
                fingerprint = ContentFingerprint.from_text(html)
                if fingerprint.md5 in self._content_seen:
                    return None, None
                metrics.record_crawl_pages(1)
                if PLAYWRIGHT_MODE != "0" and _should_use_playwright(html):
                    replacement = await _fetch_with_playwright(str(response.url), candidate)
                    if replacement:
                        fingerprint = replacement.fingerprint
                        if fingerprint.md5 in self._content_seen:
                            return None, None
                        self._content_seen.add(fingerprint.md5)
                        return replacement, None
                outlinks = _extract_outlinks(str(response.url), html)
                self._content_seen.add(fingerprint.md5)
                sources = extract_sources(html, str(response.url))
                if candidate.is_source and status >= 400:
                    return None, {"reason": str(status), "status": status}
                return PageResult(
                    url=str(response.url),
                    status=status,
                    html=html,
                    title=title,
                    fetched_at=time.time(),
                    fingerprint=fingerprint,
                    outlinks=outlinks,
                    sources=sources,
                    is_source=candidate.is_source,
                    parent_url=candidate.parent_url,
                ), None
            except Exception as exc:
                reason = "network"
                if isinstance(exc, asyncio.TimeoutError):
                    reason = "timeout"
                elif httpx is not None and isinstance(exc, getattr(httpx, "TimeoutException", ())):
                    reason = "timeout"
                last_failure = {"reason": reason, "detail": str(exc)}
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 8.0)
        if last_failure:
            LOGGER.debug("failed to fetch %s: %s", url, last_failure.get("detail", "error"))
        return None, last_failure

    async def _handle_sources(
        self,
        candidate: Candidate,
        result: PageResult,
        queue: asyncio.Queue[Candidate],
    ) -> None:
        if not self.source_budget or not result.sources:
            return
        depth = max(0, candidate.depth) + 1
        per_page_limit = max(1, self.source_config.max_sources_per_page)
        allowed_links: list[SourceLink] = []
        budget_exhausted = False
        for link in result.sources[:per_page_limit]:
            try:
                if not self.source_budget.can_follow(result.url, link.url, kind=link.kind, depth=depth):
                    self.source_stats["skipped"] += 1
                    continue
            except BudgetExceeded:
                budget_exhausted = True
                break
            if link.url in self._queued_urls or link.url in self.visited:
                self.source_stats["skipped"] += 1
                continue
            self._queued_urls.add(link.url)
            self.source_budget.record_follow()
            await queue.put(
                Candidate(
                    url=link.url,
                    source="source",
                    weight=max(candidate.weight * 0.8, 0.1),
                    score=candidate.score,
                    depth=depth,
                    is_source=True,
                    parent_url=result.url,
                )
            )
            allowed_links.append(link)
        if allowed_links:
            self.source_stats["enqueued"] += len(allowed_links)
            if self._record_source_links:
                try:
                    self._record_source_links(result.url, allowed_links, True)
                except Exception:  # pragma: no cover - logging only
                    LOGGER.debug("failed to persist source links for %s", result.url, exc_info=True)
        if budget_exhausted:
            self.source_stats["budget_exhausted"] = True

    def _handle_source_failure(self, candidate: Candidate, failure: dict[str, object]) -> None:
        self.source_stats["skipped"] += 1
        if not self._record_missing_source:
            return
        parent = candidate.parent_url
        if not parent:
            return
        reason = str(failure.get("reason", "unknown"))
        status_value = failure.get("status")
        http_status = None
        if isinstance(status_value, int):
            http_status = status_value
        next_action_value = failure.get("next_action")
        next_action = str(next_action_value) if isinstance(next_action_value, str) else None
        notes_value = failure.get("detail")
        notes = str(notes_value) if isinstance(notes_value, str) else None
        try:
            self._record_missing_source(parent, candidate.url, reason, http_status, next_action, notes)
        except Exception:  # pragma: no cover - logging only
            LOGGER.debug("failed to record missing source %s", candidate.url, exc_info=True)

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
                                "sources": [
                                    {"url": link.url, "kind": link.kind}
                                    for link in result.sources
                                ],
                                "is_source": bool(result.is_source),
                                "parent_url": result.parent_url,
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
