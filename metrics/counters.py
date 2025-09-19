"""Derived metrics for monitoring crawl coverage and freshness."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict


@dataclass
class QueryStats:
    total: int = 0
    with_results: int = 0
    focused_triggers: int = 0
    total_latency_ms: float = 0.0

    def record(self, results_count: int, triggered: bool, latency_ms: float) -> None:
        self.total += 1
        if results_count > 0:
            self.with_results += 1
        if triggered:
            self.focused_triggers += 1
        self.total_latency_ms += max(0.0, latency_ms)

    def coverage(self) -> float:
        if self.total == 0:
            return 0.0
        return round(self.with_results / self.total, 3)

    def trigger_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return round(self.focused_triggers / self.total, 3)

    def avg_latency(self) -> float:
        if self.total == 0:
            return 0.0
        return round(self.total_latency_ms / self.total, 2)


@dataclass
class MetricsState:
    query_stats: QueryStats = field(default_factory=QueryStats)
    last_index_doc_count: int = 0
    last_index_time: int = 0
    crawl_enqueued: int = 0
    llm_usage: int = 0

    def record_query(self, results_count: int, triggered: bool, latency_ms: float) -> None:
        self.query_stats.record(results_count, triggered, latency_ms)

    def record_index(self, doc_count: int, timestamp: int) -> None:
        self.last_index_doc_count = max(doc_count, 0)
        self.last_index_time = max(timestamp, 0)

    def record_enqueue(self, count: int = 1) -> None:
        self.crawl_enqueued += max(0, int(count))

    def record_llm_usage(self, count: int = 1) -> None:
        self.llm_usage += max(0, int(count))

    def freshness_lag(self) -> float:
        if not self.last_index_time:
            return 0.0
        return max(0.0, time.time() - self.last_index_time)

    def snapshot(self) -> Dict[str, object]:
        return {
            "queries_total": self.query_stats.total,
            "coverage_ratio": self.query_stats.coverage(),
            "focused_trigger_rate": self.query_stats.trigger_rate(),
            "avg_latency_ms": self.query_stats.avg_latency(),
            "index_doc_count": self.last_index_doc_count,
            "freshness_lag_seconds": round(self.freshness_lag(), 2),
            "focused_enqueued": self.crawl_enqueued,
            "llm_usage": self.llm_usage,
        }


metrics_state = MetricsState()

__all__ = ["MetricsState", "metrics_state"]
