"""High level search service coordinating Whoosh queries and focused crawls."""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional, Tuple

from search import query as query_module
from ..config import AppConfig
from ..indexer.incremental import ensure_index
from ..jobs.focused_crawl import FocusedCrawlSupervisor
from ..metrics import metrics

LOGGER = logging.getLogger(__name__)


class SearchService:
    def __init__(self, config: AppConfig, supervisor: FocusedCrawlSupervisor) -> None:
        self.config = config
        self.supervisor = supervisor
        self._lock = threading.Lock()
        self._index = None
        self._index_dir = None

    def _get_index(self):
        with self._lock:
            if self._index and self._index_dir == self.config.index_dir:
                return self._index
            self._index = ensure_index(self.config.index_dir)
            self._index_dir = self.config.index_dir
            return self._index

    def run_query(
        self,
        query: str,
        *,
        limit: int,
        use_llm: Optional[bool],
        model: Optional[str],
    ) -> Tuple[list[dict], bool]:
        start = time.perf_counter()
        ix = self._get_index()
        results = query_module.search(
            ix,
            query,
            limit=limit,
            max_limit=self.config.search_max_limit,
            max_query_length=self.config.max_query_length,
        )
        duration_ms = (time.perf_counter() - start) * 1000
        metrics.record_search_latency(duration_ms)

        q = (query or "").strip()
        scheduled = False
        if q and len(results) < self.config.smart_min_results:
            effective_use_llm = bool(use_llm)
            scheduled = self.supervisor.schedule(q, effective_use_llm, model)
        return results, scheduled

    def last_index_time(self) -> int:
        return self.supervisor.last_index_time()
