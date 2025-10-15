"""Utilities for simulating Ship-It jobs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable, Mapping, MutableMapping
import threading
import time
import uuid

StatusBuilder = Callable[
    [str, float, float, "SimulatedJob"], MutableMapping[str, object]
]


@dataclass(frozen=True)
class SimulatedPhase:
    """Represents a single phase within a simulated job."""

    name: str
    duration_s: float

    def __post_init__(self) -> None:  # pragma: no cover - defensive
        if self.duration_s < 0:
            raise ValueError("duration_s must be non-negative")


@dataclass
class SimulatedJob:
    """In-memory record for a simulated long-running job."""

    phases: tuple[SimulatedPhase, ...]
    builder: StatusBuilder
    metadata: Mapping[str, object] = field(default_factory=dict)
    start_time: float = field(default_factory=time.monotonic)
    error: str | None = None

    @property
    def total_duration(self) -> float:
        return sum(phase.duration_s for phase in self.phases)


class SimulatedJobStore:
    """Thread-safe registry for simulated job lifecycles."""

    def __init__(self) -> None:
        self._jobs: dict[str, SimulatedJob] = {}
        self._lock = threading.Lock()

    def create(
        self,
        phases: Iterable[SimulatedPhase],
        builder: StatusBuilder,
        *,
        metadata: Mapping[str, object] | None = None,
    ) -> str:
        job_id = uuid.uuid4().hex
        job = SimulatedJob(tuple(phases), builder, metadata or {})
        with self._lock:
            self._jobs[job_id] = job
        return job_id

    def get(self, job_id: str) -> SimulatedJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def snapshot(self, job_id: str) -> Mapping[str, object] | None:
        job = self.get(job_id)
        if job is None:
            return None

        elapsed = max(0.0, time.monotonic() - job.start_time)
        total_duration = max(job.total_duration, 0.0001)
        pct = min(100.0, (elapsed / total_duration) * 100.0)

        cumulative = 0.0
        current_phase = job.phases[-1].name if job.phases else "done"
        for phase in job.phases:
            cumulative += phase.duration_s
            if elapsed < cumulative:
                current_phase = phase.name
                break
        else:
            current_phase = job.phases[-1].name if job.phases else "done"

        if job.error:
            current_phase = "error"
        elif elapsed >= total_duration:
            current_phase = "done"
            pct = 100.0

        extra = job.builder(current_phase, pct, elapsed, job)
        payload: dict[str, object] = {"phase": current_phase, "pct": round(pct, 1)}
        payload.update(extra)
        if job.error:
            payload["error"] = job.error
        return payload


__all__ = ["SimulatedJobStore", "SimulatedPhase", "SimulatedJob"]
