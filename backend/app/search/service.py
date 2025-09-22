"""High level search service coordinating Whoosh queries and focused crawls."""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional, Sequence, Tuple

from search import query as query_module
from rank import blend_results, maybe_rerank
from ..config import AppConfig
from ..indexer.incremental import ensure_index
from ..jobs.focused_crawl import FocusedCrawlManager
from ..metrics import metrics
from .embedding import embed_query

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

    def reload_index(self) -> None:
        """Force the Whoosh index handle to be refreshed."""

        with self._lock:
            self._index = ensure_index(self.config.index_dir)
            self._index_dir = self.config.index_dir

    def _estimate_confidence(self, results: Sequence[dict]) -> float:
        if not results:
            return 0.0
        top_score = 0.0
        for item in results:
            blended = item.get("blended_score")
            base = item.get("score")
            try:
                candidate = float(blended if blended is not None else base or 0.0)
            except (TypeError, ValueError):
                candidate = 0.0
            if candidate > top_score:
                top_score = candidate
        if top_score <= 0:
            return 0.0
        return max(0.0, min(top_score / (1.0 + top_score), 1.0))

    def run_query(
        self,
        query: str,
        *,
        limit: int,
        use_llm: Optional[bool],
        model: Optional[str],
    ) -> Tuple[list[dict], Optional[str], dict]:
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
        confidence_threshold = getattr(self.config, "smart_confidence_threshold", 0.25)
        min_similarity = getattr(self.config, "smart_seed_min_similarity", 0.35)
        seed_limit = getattr(self.config, "smart_seed_limit", 8)
        confidence = self._estimate_confidence(blended)
        trigger_reason: Optional[str] = None
        frontier_seeds: Sequence[str] | None = None
        if q:
            effective_use_llm = llm_enabled
            should_trigger = len(blended) == 0 or confidence < confidence_threshold
            query_embedding: Optional[Sequence[float]] = None
            if should_trigger:
                trigger_reason = "no_results" if not blended else "low_confidence"
                query_embedding = embed_query(q)
                try:
                    if getattr(self.manager, "db", None) is not None:
                        seeds = self.manager.db.similar_discovery_seeds(
                            query_embedding,
                            limit=int(seed_limit),
                            min_similarity=float(min_similarity),
                        )
                        frontier_seeds = seeds
                except Exception:  # pragma: no cover - defensive logging only
                    LOGGER.debug("failed to query learned seeds for '%s'", q, exc_info=True)
            if should_trigger:
                job_id = self.manager.schedule(
                    q,
                    effective_use_llm,
                    model,
                    frontier_seeds=frontier_seeds,
                    query_embedding=query_embedding,
                )
                triggered = bool(job_id)
                if triggered:
                    metrics.record_focused_enqueue()
                else:
                    trigger_reason = None
        metrics.record_query_event(len(blended), triggered, duration_ms)
        seed_count = len(frontier_seeds) if triggered and frontier_seeds else 0
        context = {
            "confidence": confidence,
            "triggered": triggered,
            "trigger_reason": trigger_reason,
            "seed_count": seed_count,
        }
        return blended, job_id, context

    def last_index_time(self) -> int:
        return self.manager.last_index_time()
