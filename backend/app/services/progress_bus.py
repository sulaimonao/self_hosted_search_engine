"""In-process pub/sub bus for crawl progress events."""

from __future__ import annotations

import queue
import threading
from typing import Any, Dict


class ProgressBus:
    """Thread-safe queue fan-out keyed by job identifier."""

    def __init__(self) -> None:
        self._queues: Dict[str, queue.Queue[dict[str, Any]]] = {}
        self._lock = threading.RLock()

    def subscribe(self, job_id: str) -> queue.Queue[dict[str, Any]]:
        with self._lock:
            if job_id not in self._queues:
                self._queues[job_id] = queue.Queue()
            return self._queues[job_id]

    def publish(self, job_id: str, event: dict[str, Any]) -> None:
        with self._lock:
            q = self._queues.get(job_id)
        if q is None:
            return
        q.put(event)

    def ensure_queue(self, job_id: str) -> None:
        with self._lock:
            self._queues.setdefault(job_id, queue.Queue())

    def unsubscribe(
        self,
        job_id: str,
        queue_ref: queue.Queue[dict[str, Any]] | None = None,
    ) -> None:
        """Remove the queue for *job_id* when a subscriber disconnects."""

        with self._lock:
            existing = self._queues.get(job_id)
            if existing is None:
                return
            if queue_ref is not None and existing is not queue_ref:
                return
            self._queues.pop(job_id, None)


__all__ = ["ProgressBus"]
