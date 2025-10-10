"""Lightweight in-process job runner used for cold start orchestration."""

from __future__ import annotations

import contextlib
import io
import queue
import threading
import time
import traceback
import uuid
from collections import deque
from pathlib import Path
from typing import Any, Callable, Dict, Optional


class JobRunner:
    """Simple single-worker queue that persists structured logs per job."""

    def __init__(self, logs_dir: Path, *, worker_count: int = 2) -> None:
        self.logs_dir = logs_dir
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self._queue: "queue.Queue[tuple[str, Callable[[], Any]]]" = queue.Queue()
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._worker_count = max(1, int(worker_count))
        self._workers: list[threading.Thread] = []
        for index in range(self._worker_count):
            worker = threading.Thread(
                target=self._worker_loop,
                name=f"job-runner-{index}",
                daemon=True,
            )
            worker.start()
            self._workers.append(worker)

    def submit(self, job: Callable[[], Any], *, job_id: str | None = None) -> str:
        """Enqueue a job for background execution and return its identifier."""

        job_id = job_id or uuid.uuid4().hex
        log_path = self.logs_dir / f"{job_id}.log"
        with self._lock:
            self._jobs[job_id] = {
                "state": "queued",
                "log_path": log_path,
                "result": None,
                "error": None,
                "submitted_at": time.time(),
            }
        self._queue.put((job_id, job))
        return job_id

    def status(self, job_id: str) -> Dict[str, Any]:
        """Return the state and recent logs for a job."""

        with self._lock:
            info = self._jobs.get(job_id)
        if not info:
            return {"state": "unknown", "logs_tail": []}
        payload: Dict[str, Any] = {
            "state": info["state"],
            "logs_tail": self._tail(info["log_path"], limit=50),
        }
        if info.get("error"):
            payload["error"] = info["error"]
        if info.get("result") is not None:
            payload["result"] = info["result"]
        return payload

    def log_path(self, job_id: str) -> Optional[Path]:
        with self._lock:
            info = self._jobs.get(job_id)
        if not info:
            return None
        return Path(info["log_path"])

    def _tail(self, path: Path, *, limit: int) -> list[str]:
        if not path.exists():
            return []
        lines: deque[str] = deque(maxlen=limit)
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                lines.append(line.rstrip("\n"))
        return list(lines)

    def _worker_loop(self) -> None:
        while True:
            job_id, job = self._queue.get()
            start = time.time()
            with self._lock:
                info = self._jobs.get(job_id)
                if not info:
                    info = {
                        "state": "queued",
                        "log_path": self.logs_dir / f"{job_id}.log",
                        "result": None,
                        "error": None,
                    }
                    self._jobs[job_id] = info
                info["state"] = "running"
                info["started_at"] = start
            log_path = Path(info["log_path"])
            log_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                with log_path.open("a", encoding="utf-8") as log_handle:
                    writer = _TeeWriter(log_handle)
                    writer.write(f"[job:{job_id}] started at {time.ctime(start)}\n")
                    with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
                        result = job()
                    writer.write(f"[job:{job_id}] finished successfully in {time.time() - start:.2f}s\n")
                with self._lock:
                    info["state"] = "done"
                    info["result"] = result
                    info.pop("error", None)
            except Exception as exc:  # pragma: no cover - defensive branch
                error_text = "".join(traceback.format_exception(exc))
                with log_path.open("a", encoding="utf-8") as log_handle:
                    log_handle.write(error_text + "\n")
                with self._lock:
                    info["state"] = "error"
                    info["error"] = str(exc)
            finally:
                self._queue.task_done()


class _TeeWriter(io.TextIOBase):
    """File-like wrapper duplicating writes to a log handle."""

    def __init__(self, handle: io.TextIOBase) -> None:
        self._handle = handle
        self._lock = threading.Lock()

    def write(self, text: str) -> int:  # type: ignore[override]
        if not text:
            return 0
        with self._lock:
            self._handle.write(text)
            self._handle.flush()
        return len(text)

    def flush(self) -> None:  # type: ignore[override]
        with self._lock:
            self._handle.flush()

