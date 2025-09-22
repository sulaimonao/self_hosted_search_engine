"""Background worker dedicated to manual refresh requests."""

from __future__ import annotations

import queue
import threading
import time
import uuid
from collections import deque
from typing import Deque, Dict, Optional

from backend.app.config import AppConfig
from backend.app.jobs.focused_crawl import run_focused_crawl


class RefreshWorker:
    """Track and execute manual refresh jobs serially."""

    def __init__(self, config: AppConfig, *, max_history: int = 20) -> None:
        self.config = config
        self.max_history = max_history
        self._queue: "queue.Queue[str]" = queue.Queue()
        self._jobs: Dict[str, dict] = {}
        self._query_to_job: Dict[str, str] = {}
        self._history: Deque[str] = deque(maxlen=max_history)
        self._lock = threading.RLock()
        self._worker = threading.Thread(target=self._worker_loop, name="refresh-worker", daemon=True)
        self._worker.start()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def enqueue(self, query: str, *, use_llm: bool = False, model: Optional[str] = None) -> tuple[str, dict, bool]:
        """Queue a refresh for *query*; return (job_id, status, created)."""

        normalized = self._normalize_query(query)
        if not normalized:
            raise ValueError("Query must be a non-empty string")

        with self._lock:
            existing_id = self._query_to_job.get(normalized)
            if existing_id:
                existing = self._jobs.get(existing_id)
                if existing and existing.get("state") in {"queued", "running"}:
                    return existing_id, self._snapshot(existing), False

            job_id = uuid.uuid4().hex
            now = time.time()
            record = {
                "id": job_id,
                "query": query,
                "normalized_query": normalized,
                "state": "queued",
                "stage": "queued",
                "message": "Queued for refresh",
                "progress": 0,
                "use_llm": bool(use_llm),
                "model": model,
                "created_at": now,
                "started_at": None,
                "updated_at": now,
                "completed_at": None,
                "stats": {
                    "seed_count": 0,
                    "pages_fetched": 0,
                    "normalized_docs": 0,
                    "docs_indexed": 0,
                    "skipped": 0,
                    "deduped": 0,
                },
                "result": None,
                "error": None,
            }
            self._jobs[job_id] = record
            self._query_to_job[normalized] = job_id
            self._queue.put(job_id)
            return job_id, self._snapshot(record), True

    def status(self, *, job_id: Optional[str] = None, query: Optional[str] = None) -> dict:
        """Return a structured snapshot for a job or query."""

        with self._lock:
            if job_id and job_id in self._jobs:
                return {"job": self._snapshot(self._jobs[job_id])}

            if query:
                normalized = self._normalize_query(query)
                active_id = self._query_to_job.get(normalized)
                if active_id and active_id in self._jobs:
                    return {"job": self._snapshot(self._jobs[active_id])}

                for history_id in reversed(self._history):
                    job = self._jobs.get(history_id)
                    if job and job.get("normalized_query") == normalized:
                        return {"job": self._snapshot(job)}
                return {"job": None}

            active_jobs = [self._snapshot(self._jobs[jid]) for jid in self._query_to_job.values() if self._jobs.get(jid)]
            recent_jobs = [self._snapshot(self._jobs[jid]) for jid in list(self._history)[-self.max_history :]]
            return {"active": active_jobs, "recent": recent_jobs}

    # ------------------------------------------------------------------
    # Worker internals
    # ------------------------------------------------------------------
    def _worker_loop(self) -> None:
        while True:
            job_id = self._queue.get()
            try:
                self._run_job(job_id)
            finally:
                self._queue.task_done()

    def _run_job(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            job["state"] = "running"
            job["stage"] = "starting"
            job["message"] = "Starting refresh…"
            job["started_at"] = time.time()
            job["updated_at"] = job["started_at"]

        def _progress(stage: str, payload: dict) -> None:
            self._handle_progress(job_id, stage, payload)

        try:
            result = run_focused_crawl(
                job["query"],
                self.config.focused_budget,
                job.get("use_llm", False),
                job.get("model"),
                config=self.config,
                progress_callback=_progress,
            )
        except Exception as exc:  # pragma: no cover - defensive path
            self._mark_error(job_id, str(exc))
            return

        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            stats = job.get("stats", {})
            stats.update(
                {
                    "pages_fetched": result.get("pages_fetched", stats.get("pages_fetched", 0)),
                    "docs_indexed": result.get("docs_indexed", stats.get("docs_indexed", 0)),
                    "skipped": result.get("skipped", stats.get("skipped", 0)),
                    "deduped": result.get("deduped", stats.get("deduped", 0)),
                    "normalized_docs": len(result.get("normalized_docs", [])),
                }
            )
            job["stats"] = stats
            job["state"] = "done"
            job["stage"] = "complete"
            job["message"] = "Refresh complete."
            job["progress"] = 100
            job["result"] = result
            job["completed_at"] = time.time()
            job["updated_at"] = job["completed_at"]
            self._history.append(job_id)
            normalized = job.get("normalized_query")
            if normalized:
                self._query_to_job.pop(normalized, None)

    def _mark_error(self, job_id: str, error: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            job["state"] = "error"
            job["stage"] = "error"
            job["message"] = "Refresh failed."
            job["error"] = error
            job["progress"] = max(int(job.get("progress", 0)), 1)
            job["completed_at"] = time.time()
            job["updated_at"] = job["completed_at"]
            self._history.append(job_id)
            normalized = job.get("normalized_query")
            if normalized:
                self._query_to_job.pop(normalized, None)

    def _handle_progress(self, job_id: str, stage: str, payload: dict) -> None:
        message = self._stage_message(stage, payload)
        increment = self._stage_progress(stage)
        with self._lock:
            job = self._jobs.get(job_id)
            if not job or job.get("state") == "error":
                return
            job["stage"] = stage
            if message:
                job["message"] = message
            if increment is not None:
                job["progress"] = max(int(job.get("progress", 0)), increment)
            job["updated_at"] = time.time()
            stats = job.get("stats", {})
            if stage == "frontier_complete":
                stats["seed_count"] = int(payload.get("seed_count", 0) or 0)
            elif stage == "crawl_complete":
                stats["pages_fetched"] = int(payload.get("pages_fetched", 0) or 0)
            elif stage == "normalize_complete":
                stats["normalized_docs"] = int(payload.get("docs", 0) or 0)
            elif stage == "index_complete":
                stats["docs_indexed"] = int(payload.get("docs_indexed", 0) or 0)
                stats["skipped"] = int(payload.get("skipped", 0) or 0)
                stats["deduped"] = int(payload.get("deduped", 0) or 0)
            job["stats"] = stats

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _snapshot(self, job: dict) -> dict:
        payload = {
            "job_id": job.get("id"),
            "query": job.get("query"),
            "state": job.get("state"),
            "stage": job.get("stage"),
            "message": job.get("message"),
            "progress": int(job.get("progress", 0)),
            "use_llm": bool(job.get("use_llm")),
            "model": job.get("model"),
            "created_at": job.get("created_at"),
            "started_at": job.get("started_at"),
            "updated_at": job.get("updated_at"),
            "completed_at": job.get("completed_at"),
            "stats": dict(job.get("stats", {})),
        }
        if job.get("error"):
            payload["error"] = job.get("error")
        if job.get("result") is not None:
            payload["result"] = job.get("result")
        return payload

    @staticmethod
    def _normalize_query(query: str) -> str:
        return " ".join((query or "").strip().split()).lower()

    @staticmethod
    def _stage_progress(stage: str) -> Optional[int]:
        mapping = {
            "starting": 5,
            "frontier_start": 10,
            "frontier_complete": 20,
            "crawl_start": 30,
            "crawl_complete": 55,
            "normalize_start": 65,
            "normalize_complete": 75,
            "index_start": 85,
            "index_complete": 95,
            "index_skipped": 95,
            "frontier_empty": 90,
        }
        return mapping.get(stage)

    @staticmethod
    def _stage_message(stage: str, payload: dict) -> Optional[str]:
        if stage == "frontier_start":
            return "Collecting crawl seeds…"
        if stage == "frontier_complete":
            count = int(payload.get("seed_count", 0) or 0)
            return f"Planned {count} seed URL{'s' if count != 1 else ''}."
        if stage == "crawl_start":
            return "Crawling priority URLs…"
        if stage == "crawl_complete":
            pages = int(payload.get("pages_fetched", 0) or 0)
            return f"Fetched {pages} page{'s' if pages != 1 else ''}."
        if stage == "normalize_start":
            return "Normalizing new documents…"
        if stage == "normalize_complete":
            docs = int(payload.get("docs", 0) or 0)
            return f"Normalized {docs} document{'s' if docs != 1 else ''}."
        if stage == "index_start":
            return "Updating search index…"
        if stage == "index_complete":
            docs = int(payload.get("docs_indexed", 0) or 0)
            return f"Indexed {docs} document{'s' if docs != 1 else ''}."
        if stage == "index_skipped":
            return "No new documents were indexed."
        if stage == "frontier_empty":
            return "No candidate URLs available for this query."
        return None

