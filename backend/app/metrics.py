"""In-memory metrics registry exposed via the API."""

from __future__ import annotations

import math
import statistics
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from metrics.counters import metrics_state


@dataclass
class Counter:
    value: int = 0

    def incr(self, amount: int = 1) -> None:
        self.value += int(amount)


@dataclass
class Histogram:
    samples: List[float] = field(default_factory=list)
    max_samples: int = 500

    def add(self, value: float) -> None:
        self.samples.append(float(value))
        if len(self.samples) > self.max_samples:
            # Keep the most recent ``max_samples`` values to bound memory usage.
            excess = len(self.samples) - self.max_samples
            del self.samples[0:excess]

    def percentiles(self) -> Dict[str, float]:
        if not self.samples:
            return {"p50": 0.0, "p95": 0.0}

        ordered = sorted(self.samples)
        median = statistics.median(ordered)

        if len(ordered) == 1:
            percentile_95 = float(ordered[0])
        else:
            position = 0.95 * (len(ordered) - 1)
            lower_index = int(math.floor(position))
            upper_index = int(math.ceil(position))
            lower_value = ordered[lower_index]
            upper_value = ordered[upper_index]
            if lower_index == upper_index:
                percentile_95 = float(lower_value)
            else:
                weight = position - lower_index
                percentile_95 = float(
                    lower_value + (upper_value - lower_value) * weight
                )

        return {"p50": float(median), "p95": percentile_95}


class MetricsRegistry:
    """Thread-safe collector for application-level metrics."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.search_latency_ms = Histogram()
        self.crawl_pages_fetched = Counter()
        self.llm_seed_ms = Histogram()
        self.index_docs_added = Counter()
        self.index_docs_skipped = Counter()
        self.dedupe_hits = Counter()
        self.playwright_uses = Counter()

    def snapshot(self) -> Dict[str, object]:
        with self._lock:
            latency = self.search_latency_ms.percentiles()
            llm = self.llm_seed_ms.percentiles()
            snapshot = metrics_state.snapshot()
            snapshot.update(
                {
                    "search_latency_ms": latency,
                    "crawl_pages_fetched": self.crawl_pages_fetched.value,
                    "llm_seed_ms": llm,
                    "index_docs_added": self.index_docs_added.value,
                    "index_docs_skipped": self.index_docs_skipped.value,
                    "dedupe_hits": self.dedupe_hits.value,
                    "playwright_uses": self.playwright_uses.value,
                }
            )
            return snapshot

    def record_search_latency(self, ms: float) -> None:
        with self._lock:
            self.search_latency_ms.add(ms)

    def record_crawl_pages(self, count: int) -> None:
        with self._lock:
            self.crawl_pages_fetched.incr(count)

    def record_llm_seed_time(self, ms: float) -> None:
        with self._lock:
            self.llm_seed_ms.add(ms)

    def record_index_results(self, added: int, skipped: int, deduped: int, total_docs: Optional[int] = None) -> None:
        with self._lock:
            self.index_docs_added.incr(added)
            self.index_docs_skipped.incr(skipped)
            self.dedupe_hits.incr(deduped)
            if total_docs is not None:
                metrics_state.record_index(total_docs, int(time.time()))

    def record_playwright_use(self, count: int = 1) -> None:
        with self._lock:
            self.playwright_uses.incr(count)

    def record_query_event(self, results_count: int, triggered: bool, latency_ms: float) -> None:
        metrics_state.record_query(results_count, triggered, latency_ms)

    def record_focused_enqueue(self, count: int = 1) -> None:
        metrics_state.record_enqueue(count)

    def record_llm_usage_event(self, count: int = 1) -> None:
        metrics_state.record_llm_usage(count)


metrics = MetricsRegistry()
