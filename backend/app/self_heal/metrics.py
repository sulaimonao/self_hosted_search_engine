from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict

from backend.app.services.progress_bus import ProgressBus

METRICS_PATH = Path(os.getenv("SELF_HEAL_METRICS", "data/self_heal/metrics.json"))


@dataclass
class SelfHealMetrics:
    planner_calls_total: int = 0
    planner_fallback_count: int = 0
    rule_hits_count: int = 0
    headless_runs_count: int = 0

    def to_dict(self) -> Dict[str, int]:
        return asdict(self)


class MetricsStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._metrics = SelfHealMetrics()
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return
        if not isinstance(payload, dict):
            return
        metrics = SelfHealMetrics()
        for key in metrics.to_dict():
            value = payload.get(key)
            if isinstance(value, int) and value >= 0:
                setattr(metrics, key, value)
        self._metrics = metrics

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._path.write_text(json.dumps(self._metrics.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def increment(self, key: str, amount: int = 1) -> Dict[str, int]:
        with self._lock:
            if not hasattr(self._metrics, key):
                raise AttributeError(f"unknown metric: {key}")
            current = getattr(self._metrics, key)
            setattr(self._metrics, key, max(0, int(current) + int(amount)))
            self._save()
            return self.snapshot()

    def snapshot(self) -> Dict[str, int]:
        with self._lock:
            return self._metrics.to_dict().copy()


_store = MetricsStore(METRICS_PATH)


def record_event(key: str, amount: int = 1, *, bus: ProgressBus | None = None) -> Dict[str, int]:
    snapshot = _store.increment(key, amount)
    if bus is not None:
        try:
            bus.publish(
                "__diagnostics__",
                {
                    "stage": "self_heal.metrics",
                    "message": f"{key}+={amount}",
                    "metrics": snapshot,
                },
            )
        except Exception:  # pragma: no cover - best effort
            pass
    return snapshot


def metrics_snapshot() -> Dict[str, int]:
    return _store.snapshot()


__all__ = ["record_event", "metrics_snapshot", "METRICS_PATH", "SelfHealMetrics"]
