"""High level search service coordinating Whoosh queries and focused crawls."""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional, Tuple

from search import query as query_module
from rank import blend_results, maybe_rerank
from ..config import AppConfig
from ..indexer.incremental import ensure_index
from ..jobs.focused_crawl import FocusedCrawlManager
from ..metrics import metrics

LOGGER = logging.getLogger(__name__)


class SearchService:
    def __init__(self, config: AppConfig, manager: FocusedCrawlManager) -> None:
        self.config = config
        self.manager = manager
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
    ) -> Tuple[list[dict], Optional[str]]:
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
        blended = blend_results(results)
        llm_enabled = self.config.use_llm_rerank if use_llm is None else bool(use_llm)
        if llm_enabled:
            reranked = maybe_rerank(q, blended, enabled=True, model=model)
            if reranked is not blended:
                metrics.record_llm_usage_event()
            blended = reranked

        job_id: Optional[str] = None
        triggered = False
        if q:
            effective_use_llm = llm_enabled
            job_id = self.manager.schedule(q, effective_use_llm, model)
            triggered = bool(job_id)
            if triggered:
                metrics.record_focused_enqueue()
        metrics.record_query_event(len(blended), triggered, duration_ms)
        return blended, job_id

    def last_index_time(self) -> int:
        return self.manager.last_index_time()
