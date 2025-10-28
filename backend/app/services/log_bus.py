"""Lightweight pub/sub bus for agent trace events."""

from __future__ import annotations

import json
import queue
import threading
import time
from typing import Any, Iterable


class AgentLogBus:
    """Thread-safe fan-out queue for agent log events."""

    def __init__(self, *, max_queue_size: int = 512) -> None:
        self._max_queue_size = max_queue_size
        self._subscribers: list[queue.Queue[dict[str, Any]]] = []
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Subscription management
    # ------------------------------------------------------------------
    def subscribe(self) -> queue.Queue[dict[str, Any]]:
        """Register a new subscriber queue."""

        stream: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=self._max_queue_size)
        with self._lock:
            self._subscribers.append(stream)
        return stream

    def unsubscribe(self, stream: queue.Queue[dict[str, Any]] | None) -> None:
        if stream is None:
            return
        with self._lock:
            try:
                self._subscribers.remove(stream)
            except ValueError:
                return
        try:
            stream.put_nowait({"type": "__closed__"})
        except Exception:
            # queue may be full or closed; ignore
            pass

    # ------------------------------------------------------------------
    # Event delivery
    # ------------------------------------------------------------------
    def publish(self, event: dict[str, Any]) -> None:
        payload = self._prepare_event(event)
        with self._lock:
            subscribers: Iterable[queue.Queue[dict[str, Any]]] = tuple(self._subscribers)
        for stream in subscribers:
            self._deliver(stream, payload)

    def _prepare_event(self, event: dict[str, Any]) -> dict[str, Any]:
        payload = dict(event)
        payload.setdefault("timestamp", time.time())
        # Ensure the payload is JSON-serialisable; fall back to string
        for key, value in list(payload.items()):
            try:
                json.dumps(value)
            except TypeError:
                payload[key] = str(value)
        return payload

    def _deliver(self, stream: queue.Queue[dict[str, Any]], event: dict[str, Any]) -> None:
        try:
            stream.put_nowait(event)
            return
        except queue.Full:
            # Drop the oldest item then retry once
            try:
                stream.get_nowait()
            except queue.Empty:
                pass
            try:
                stream.put_nowait(event)
                return
            except queue.Full:
                pass
        except Exception:
            return


__all__ = ["AgentLogBus"]
