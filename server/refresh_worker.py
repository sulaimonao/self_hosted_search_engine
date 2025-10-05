"""Background worker dedicated to manual refresh requests."""

from __future__ import annotations

import logging
import queue
import threading
import time
import uuid
from collections import deque
from typing import TYPE_CHECKING, Deque, Dict, Optional, Sequence

from backend.app.config import AppConfig
from backend.app.db import AppStateDB
from backend.app.jobs.focused_crawl import run_focused_crawl
from backend.app.services.progress_bus import ProgressBus


if TYPE_CHECKING:  # pragma: no cover - imported for typing only
    from backend.app.search.service import SearchService
    from server.learned_web_db import LearnedWebDB


LOGGER = logging.getLogger(__name__)


class RefreshWorker:
    """Track and execute manual refresh jobs serially."""

    DEFAULT_FRONTIER_DEPTH = 4

    def __init__(
        self,
        config: AppConfig,
        *,
        max_history: int = 20,
        search_service: Optional["SearchService"] = None,
        db: Optional["LearnedWebDB"] = None,
        state_db: Optional[AppStateDB] = None,
        progress_bus: Optional[ProgressBus] = None,
    ) -> None:
        self.config = config
        self.max_history = max_history
        self._search_service = search_service
        self._db = db
        self._state_db = state_db
        self._progress_bus = progress_bus
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
    def enqueue(
        self,
        query: str,
        *,
        use_llm: bool = False,
        model: Optional[str] = None,
        budget: Optional[int] = None,
        depth: Optional[int] = None,
        force: bool = False,
        seeds: Optional[Sequence[str]] = None,
    ) -> tuple[str, dict, bool]:
        """Queue a refresh for *query*; return (job_id, status, created)."""

        normalized = self._normalize_query(query)
        if not normalized:
            raise ValueError("Query must be a non-empty string")

        effective_budget = self._resolve_budget(budget)
        frontier_depth = self._resolve_depth(depth)
        seed_list = self._clean_seeds(seeds)

        with self._lock:
            existing_id = self._query_to_job.get(normalized)
            if existing_id and not force:
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
                "budget": effective_budget,
                "depth": frontier_depth,
                "force": bool(force),
                "seeds": seed_list,
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
                    "fetched": 0,
                    "updated": 0,
                    "embedded": 0,
                    "new_domains": 0,
                },
                "result": None,
                "error": None,
                "discovery": None,
            }
            self._jobs[job_id] = record
            self._query_to_job[normalized] = job_id
            self._queue.put(job_id)
            if self._state_db is not None:
                primary_seed = seed_list[0] if seed_list else None
                self._state_db.record_crawl_job(
                    job_id,
                    seed=primary_seed,
                    query=query,
                    normalized_path=str(self.config.normalized_path),
                )
            if self._progress_bus is not None:
                self._progress_bus.ensure_queue(job_id)
                self._progress_bus.publish(
                    job_id,
                    {
                        "stage": "queued",
                        "job_id": job_id,
                        "query": query,
                        "seeds": seed_list or [],
                    },
                )
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
            budget = int(job.get("budget") or self.config.focused_budget)
            depth = int(job.get("depth") or self.DEFAULT_FRONTIER_DEPTH)
            manual_seeds = list(job.get("seeds") or [])

        state_db = self._state_db
        progress_bus = self._progress_bus
        if state_db is not None:
            state_db.update_crawl_status(job_id, "running")
        if progress_bus is not None:
            progress_bus.publish(
                job_id,
                {"stage": "running", "job_id": job_id, "query": job.get("query")},
            )

        def _progress(stage: str, payload: dict) -> None:
            payload_dict = dict(payload or {})
            stats_snapshot = None
            if state_db is not None:
                stats_snapshot = state_db.record_crawl_event(job_id, stage, payload_dict)
            event = dict(payload_dict)
            event["stage"] = stage
            event["job_id"] = job_id
            if stats_snapshot is not None:
                event["stats"] = stats_snapshot
            if progress_bus is not None:
                progress_bus.publish(job_id, event)
            self._handle_progress(job_id, stage, payload_dict)

        try:
            result = run_focused_crawl(
                job["query"],
                budget,
                job.get("use_llm", False),
                job.get("model"),
                config=self.config,
                manual_seeds=manual_seeds or None,
                frontier_depth=depth,
                progress_callback=_progress,
                db=self._db,
                state_db=state_db,
                job_id=job_id,
            )
        except Exception as exc:  # pragma: no cover - defensive path
            self._mark_error(job_id, str(exc))
            return

        if self._search_service is not None:
            try:
                self._search_service.reload_index()
            except Exception:  # pragma: no cover - defensive logging only
                LOGGER.exception("failed to reload search index after refresh")

        stats_payload = {
            "pages_fetched": int(result.get("pages_fetched", 0) or 0),
            "docs_indexed": int(result.get("docs_indexed", 0) or 0),
            "skipped": int(result.get("skipped", 0) or 0),
            "deduped": int(result.get("deduped", 0) or 0),
            "embedded": int(result.get("embedded", 0) or 0),
            "new_domains": int(result.get("new_domains", 0) or 0),
        }
        preview_payload = result.get("normalized_preview") or []
        normalized_path = result.get("normalized_path")
        if state_db is not None:
            state_db.update_crawl_status(
                job_id,
                "success",
                stats=stats_payload,
                preview=preview_payload,
                normalized_path=str(normalized_path) if normalized_path else None,
            )
            state_db.record_crawl_event(job_id, "done", {"stats": stats_payload})
        if progress_bus is not None:
            progress_bus.publish(
                job_id,
                {"stage": "done", "job_id": job_id, "stats": stats_payload},
            )

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
                    "fetched": result.get("pages_fetched", stats.get("fetched", 0)),
                    "updated": result.get("docs_indexed", stats.get("updated", 0)),
                    "embedded": result.get("embedded", stats.get("embedded", 0)),
                    "new_domains": result.get("new_domains", stats.get("new_domains", 0)),
                }
            )
            job["stats"] = stats
            if result.get("discovery") is not None:
                job["discovery"] = result.get("discovery")
            job["state"] = "done"
            job["stage"] = "complete"
            job["message"] = "Refresh complete."
            job["progress"] = 100
            job["result"] = result
            job["completed_at"] = time.time()
            job["updated_at"] = job["completed_at"]
            self._history.append(job_id)
            normalized = job.get("normalized_query")
            if normalized and self._query_to_job.get(normalized) == job_id:
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
            if normalized and self._query_to_job.get(normalized) == job_id:
                self._query_to_job.pop(normalized, None)
        if self._state_db is not None:
            self._state_db.update_crawl_status(job_id, "error", error=error)
            self._state_db.record_crawl_event(job_id, "error", {"error": error})
        if self._progress_bus is not None:
            self._progress_bus.publish(
                job_id,
                {"stage": "error", "job_id": job_id, "error": error},
            )

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
                if "new_domains" in payload:
                    stats["new_domains"] = int(payload.get("new_domains", 0) or 0)
                if "embedded" in payload:
                    stats["embedded"] = int(payload.get("embedded", 0) or 0)
                seeds_preview = list(payload.get("seeds", []) or [])
                if len(seeds_preview) > 20:
                    seeds_preview = seeds_preview[:20]
                discovery_snapshot = {
                    "mode": payload.get("mode"),
                    "seeds": seeds_preview,
                    "sources": payload.get("sources"),
                    "budget": job.get("budget"),
                    "depth": job.get("depth"),
                    "seed_count": stats.get("seed_count", 0),
                }
                job["discovery"] = discovery_snapshot
            elif stage == "crawl_complete":
                stats["pages_fetched"] = int(payload.get("pages_fetched", 0) or 0)
                stats["fetched"] = stats["pages_fetched"]
            elif stage == "normalize_complete":
                stats["normalized_docs"] = int(payload.get("docs", 0) or 0)
            elif stage == "index_complete":
                stats["docs_indexed"] = int(payload.get("docs_indexed", 0) or 0)
                stats["skipped"] = int(payload.get("skipped", 0) or 0)
                stats["deduped"] = int(payload.get("deduped", 0) or 0)
                stats["updated"] = stats["docs_indexed"]
            elif stage == "index_skipped":
                stats["updated"] = 0
            job["stats"] = stats

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _resolve_budget(self, candidate: Optional[int]) -> int:
        if candidate is None:
            return max(1, int(getattr(self.config, "focused_budget", 1)))
        try:
            value = int(candidate)
        except (TypeError, ValueError):
            raise ValueError("Budget must be a positive integer") from None
        if value <= 0:
            raise ValueError("Budget must be a positive integer")
        return value

    def _resolve_depth(self, candidate: Optional[int]) -> int:
        if candidate is None:
            return self.DEFAULT_FRONTIER_DEPTH
        try:
            value = int(candidate)
        except (TypeError, ValueError):
            raise ValueError("Depth must be a positive integer") from None
        if value <= 0:
            raise ValueError("Depth must be a positive integer")
        return value

    @staticmethod
    def _clean_seeds(seeds: Optional[Sequence[str]]) -> Optional[list[str]]:
        if not seeds:
            return None
        cleaned: list[str] = []
        seen: set[str] = set()
        for item in seeds:
            if not isinstance(item, str):
                continue
            candidate = item.strip()
            if not candidate or candidate in seen:
                continue
            cleaned.append(candidate)
            seen.add(candidate)
        return cleaned or None

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
            "budget": job.get("budget"),
            "depth": job.get("depth"),
            "force": bool(job.get("force", False)),
            "seeds": list(job.get("seeds", []) or []),
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
        if job.get("discovery") is not None:
            payload["discovery"] = job.get("discovery")
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

