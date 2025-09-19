"""Robots.txt helper with caching."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Dict
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

try:
    import httpx
except ImportError:  # pragma: no cover - optional dependency
    httpx = None  # type: ignore

LOGGER = logging.getLogger(__name__)


@dataclass
class _CacheEntry:
    parser: RobotFileParser
    fetched_at: float


class RobotsCache:
    """Cache robots.txt lookups across crawling sessions."""

    def __init__(
        self,
        *,
        respect: bool = True,
        ttl: int = 3600,
        user_agent: str = "SelfHostedSearchBot/1.0",
    ) -> None:
        self.respect = respect
        self.ttl = max(60, ttl)
        self.user_agent = user_agent
        self._cache: Dict[str, _CacheEntry] = {}
        self._lock = asyncio.Lock()

    def _key(self, url: str) -> str:
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")

    async def allowed_async(self, client: httpx.AsyncClient, url: str) -> bool:
        if not self.respect:
            return True
        key = self._key(url)
        async with self._lock:
            entry = self._cache.get(key)
            if entry and (time.time() - entry.fetched_at) < self.ttl:
                return entry.parser.can_fetch(self.user_agent, url)
        robots_url = f"{key}/robots.txt"
        try:
            response = await client.get(robots_url, timeout=5.0)
            text = response.text if response.status_code < 400 else ""
        except Exception:
            text = ""
        parser = RobotFileParser()
        parser.set_url(robots_url)
        parser.parse(text.splitlines())
        async with self._lock:
            self._cache[key] = _CacheEntry(parser=parser, fetched_at=time.time())
        return parser.can_fetch(self.user_agent, url)

    def allowed(self, url: str, fetcher=None) -> bool:
        if not self.respect:
            return True
        key = self._key(url)
        entry = self._cache.get(key)
        if entry and (time.time() - entry.fetched_at) < self.ttl:
            return entry.parser.can_fetch(self.user_agent, url)
        robots_url = f"{key}/robots.txt"
        text = ""
        if fetcher:
            try:
                text = fetcher(robots_url)
            except Exception:
                text = ""
        parser = RobotFileParser()
        parser.set_url(robots_url)
        parser.parse((text or "").splitlines())
        self._cache[key] = _CacheEntry(parser=parser, fetched_at=time.time())
        return parser.can_fetch(self.user_agent, url)


__all__ = ["RobotsCache"]
