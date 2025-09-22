"""High level search service coordinating Whoosh queries and focused crawls."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Optional, Sequence

from search import query as query_module
from rank import blend_results, maybe_rerank
from ..config import AppConfig
from ..indexer.incremental import ensure_index
from ..jobs.focused_crawl import FocusedCrawlManager
from ..metrics import metrics
from .learned_web import LearnedWebStore

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class SearchRunResult:
    results: list[dict]
    job_id: Optional[str]
    triggered: bool
    confidence: float
    trigger_reason: Optional[str]
    trigger_attempted: bool
    frontier_seeds: tuple[str, ...] = ()


class SearchService:
    def __init__(
        self,
        config: AppConfig,
        manager: FocusedCrawlManager,
        learned_store: Optional[LearnedWebStore] = None,
    ) -> None:
        self.config = config
        self.manager = manager
        self.learned_store = learned_store
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
    ) -> SearchRunResult:
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

        confidence = self._estimate_confidence(blended)
        job_id: Optional[str] = None
        triggered = False
        trigger_attempted = False
        trigger_reason: Optional[str] = None
        seeds: list[str] = []
        if q:
            effective_use_llm = llm_enabled
            hits = len(blended)
            if hits == 0:
                trigger_attempted = True
                trigger_reason = "no_results"
            elif confidence < max(0.0, float(self.config.smart_min_confidence)):
                trigger_attempted = True
                trigger_reason = "low_confidence"

            if trigger_attempted:
                LOGGER.info(
                    "focused crawl trigger attempt for '%s' (hits=%d confidence=%.3f reason=%s)",
                    q,
                    hits,
                    confidence,
                    trigger_reason,
                )
                if self.learned_store:
                    try:
                        seeds = self.learned_store.similar_urls(
                            q,
                            limit=self.config.learned_seed_limit,
                            min_similarity=self.config.learned_min_similarity,
                        )
                    except Exception:  # pragma: no cover - defensive logging only
                        LOGGER.exception("learned web lookup failed", exc_info=True)
                        seeds = []
                job_id = self.manager.schedule(
                    q,
                    effective_use_llm,
                    model,
                    extra_seeds=seeds or None,
                )
                triggered = bool(job_id)
                if triggered:
                    metrics.record_focused_enqueue()
                else:
                    seeds = []
        metrics.record_query_event(len(blended), triggered, duration_ms)
        return SearchRunResult(
            results=blended,
            job_id=job_id,
            triggered=triggered,
            confidence=confidence,
            trigger_reason=trigger_reason if trigger_attempted else None,
            trigger_attempted=trigger_attempted,
            frontier_seeds=tuple(seeds),
        )

    def last_index_time(self) -> int:
        return self.manager.last_index_time()

    def _estimate_confidence(self, results: Sequence[dict]) -> float:
        if not results:
            return 0.0
        scores: list[float] = []
        for item in results[:5]:
            base = item.get("blended_score", item.get("score", 0.0))
            try:
                score = float(base)
            except (TypeError, ValueError):
                continue
            if score > 0:
                scores.append(score)
        if not scores:
            return 0.0
        top = max(scores)
        total = sum(scores)
        if total <= 0:
            return 0.0
        confidence = top / total
        return max(0.0, min(1.0, confidence))
