"""Custom Scrapy middlewares for polite crawling."""

from __future__ import annotations

import logging
import os

LOGGER = logging.getLogger(__name__)


class AdaptiveDelayMiddleware:
    """Adjust per-domain download delays when servers signal overload."""

    def __init__(self, crawler) -> None:
        self.crawler = crawler
        self.base_delay = float(os.getenv("CRAWL_DOWNLOAD_DELAY", "0.25"))
        self.max_delay = float(os.getenv("CRAWL_BACKOFF_MAX", "8.0"))
        self.decay = float(os.getenv("CRAWL_BACKOFF_DECAY", "0.5"))

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def _update_delay(self, slot, factor: float) -> None:
        if slot is None:
            return
        new_delay = min(self.max_delay, max(self.base_delay, slot.delay * factor))
        if abs(new_delay - slot.delay) > 1e-3:
            LOGGER.debug("adaptive delay updated: %s -> %.3fs", slot.key, new_delay)
        slot.delay = new_delay

    def process_response(self, request, response, spider):  # type: ignore[override]
        slot = self.crawler.engine.downloader.slots.get(request.meta.get("download_slot"))
        if response.status in {429, 503}:
            self._update_delay(slot, 2.0)
        else:
            # Gradually decay back towards the base delay.
            self._update_delay(slot, self.decay)
        return response

    def process_exception(self, request, exception, spider):  # type: ignore[override]
        slot = self.crawler.engine.downloader.slots.get(request.meta.get("download_slot"))
        self._update_delay(slot, 1.5)
        return None


__all__ = ["AdaptiveDelayMiddleware"]
