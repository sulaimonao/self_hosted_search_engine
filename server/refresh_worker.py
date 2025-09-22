"""Background worker dedicated to manual refresh requests."""

from __future__ import annotations

import hashlib
import logging
import queue
import threading
import time
import uuid
from collections import deque
from typing import TYPE_CHECKING, Deque, Dict, Optional, Sequence
from urllib.parse import urlparse

from backend.app.config import AppConfig
from backend.app.jobs.focused_crawl import run_focused_crawl
from crawler.frontier import Candidate
from server.discover import DiscoveryEngine

if TYPE_CHECKING:  # pragma: no cover - import cycles avoided at runtime
    from backend.app.search.service import SearchService
    from engine.data.store import VectorStore
    from engine.indexing.chunk import TokenChunker
    from engine.indexing.embed import OllamaEmbedder


LOGGER = logging.getLogger(__name__)


class RefreshWorker:
    """Track and execute manual refresh jobs serially."""

    def __init__(
        self,
        config: AppConfig,
        *,
        max_history: int = 20,
        search_service: "SearchService" | None = None,
    ) -> None:
        self.config = config
        self.max_history = max_history
        self._queue: "queue.Queue[str]" = queue.Queue()
        self._jobs: Dict[str, dict] = {}
        self._query_to_job: Dict[str, str] = {}
        self._history: Deque[str] = deque(maxlen=max_history)
        self._lock = threading.RLock()
        self._search_service = search_service
        self._discovery = DiscoveryEngine()
        self._vector_store: "VectorStore | None" = None
        self._embedder: "OllamaEmbedder | None" = None
        self._chunker: "TokenChunker | None" = None
        self._frontier_depth_default = 4
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

        job_budget = self._coerce_positive_int(budget)
        job_depth = self._coerce_positive_int(depth)
        seed_list = self._sanitize_seeds(seeds)

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
                "options": {
                    "budget": job_budget,
                    "depth": job_depth,
                    "force": bool(force),
                    "seeds": seed_list,
                },
                "created_at": now,
                "started_at": None,
                "updated_at": now,
                "completed_at": None,
                "stats": {
                    "seed_count": 0,
                    "new_domains": 0,
                    "pages_fetched": 0,
                    "fetched": 0,
                    "normalized_docs": 0,
                    "docs_indexed": 0,
                    "updated": 0,
                    "skipped": 0,
                    "deduped": 0,
                    "embedded": 0,
                },
                "result": None,
                "error": None,
                "frontier": None,
            }
            self._jobs[job_id] = record
            self._query_to_job[normalized] = job_id
            self._queue.put(job_id)
            return job_id, self._snapshot(record), True

    def configure_vector_pipeline(
        self,
        *,
        vector_store: "VectorStore | None" = None,
        embedder: "OllamaEmbedder | None" = None,
        chunker: "TokenChunker | None" = None,
    ) -> None:
        """Attach the optional embedding pipeline used for semantic refreshes."""

        with self._lock:
            self._vector_store = vector_store
            self._embedder = embedder
            self._chunker = chunker

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
            options = dict(job.get("options") or {})
            use_llm = bool(job.get("use_llm", False))
            model = job.get("model")
            query = job.get("query", "")

        budget = self._effective_budget(options.get("budget"))
        depth = self._effective_depth(options.get("depth"))
        manual_seeds: Sequence[str] = options.get("seeds", [])

        seed_candidates, frontier_meta = self._prepare_frontier(
            query,
            budget=budget,
            depth=depth,
            use_llm=use_llm,
            model=model,
            manual_seeds=manual_seeds,
        )

        if frontier_meta:
            with self._lock:
                job = self._jobs.get(job_id)
                if job:
                    job["frontier"] = frontier_meta
                    stats = dict(job.get("stats", {}))
                    stats["seed_count"] = frontier_meta.get("seed_count", stats.get("seed_count", 0))
                    stats["new_domains"] = frontier_meta.get("new_domains", stats.get("new_domains", 0))
                    job["stats"] = stats

        def _progress(stage: str, payload: dict) -> None:
            self._handle_progress(job_id, stage, payload)

        try:
            result = run_focused_crawl(
                query,
                budget,
                use_llm,
                model,
                config=self.config,
                progress_callback=_progress,
                seed_candidates=seed_candidates,
                frontier_depth=depth,
            )
        except Exception as exc:  # pragma: no cover - defensive path
            LOGGER.exception("refresh job failed for '%s'", query, exc_info=True)
            self._mark_error(job_id, str(exc))
            return

        normalized_docs = result.get("normalized_docs", [])
        embedded = 0
        if normalized_docs and self._vector_pipeline_ready():
            try:
                _progress("embedding_start", {"docs": len(normalized_docs)})
                embedded = self._embed_documents(normalized_docs)
            except Exception:  # pragma: no cover - defensive logging only
                LOGGER.exception("failed to embed documents for '%s'", query, exc_info=True)
            finally:
                _progress("embedding_complete", {"embedded": embedded})

        discovery_meta = result.get("discovery") or frontier_meta

        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            stats = job.get("stats", {})
            stats["pages_fetched"] = int(result.get("pages_fetched", stats.get("pages_fetched", 0)) or 0)
            stats["fetched"] = stats["pages_fetched"]
            stats["docs_indexed"] = int(result.get("docs_indexed", stats.get("docs_indexed", 0)) or 0)
            stats["updated"] = stats["docs_indexed"]
            stats["skipped"] = int(result.get("skipped", stats.get("skipped", 0)) or 0)
            stats["deduped"] = int(result.get("deduped", stats.get("deduped", 0)) or 0)
            stats["normalized_docs"] = int(len(normalized_docs))
            stats["embedded"] = max(int(stats.get("embedded", 0) or 0), int(embedded))
            if discovery_meta:
                stats["seed_count"] = discovery_meta.get("seed_count", stats.get("seed_count", 0))
                stats["new_domains"] = discovery_meta.get("new_domains", stats.get("new_domains", 0))
            job["stats"] = stats
            job["state"] = "done"
            job["stage"] = "complete"
            job["message"] = "Refresh complete."
            job["progress"] = 100
            job_result = dict(result)
            if discovery_meta:
                job_result["discovery"] = discovery_meta
            job_result["embedded"] = embedded
            job["result"] = job_result
            job["frontier"] = discovery_meta
            job["completed_at"] = time.time()
            job["updated_at"] = job["completed_at"]
            self._history.append(job_id)
            normalized = job.get("normalized_query")
            if normalized:
                self._query_to_job.pop(normalized, None)

        self._trigger_hot_reload()

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
                stats["new_domains"] = int(payload.get("new_domains", stats.get("new_domains", 0)) or 0)
                frontier = dict(job.get("frontier") or {})
                frontier.update(payload)
                frontier.setdefault("seed_count", stats.get("seed_count", 0))
                frontier.setdefault("new_domains", stats.get("new_domains", 0))
                job["frontier"] = frontier
            elif stage == "crawl_complete":
                stats["pages_fetched"] = int(payload.get("pages_fetched", 0) or 0)
                stats["fetched"] = stats["pages_fetched"]
            elif stage == "normalize_complete":
                stats["normalized_docs"] = int(payload.get("docs", 0) or 0)
            elif stage == "index_complete":
                stats["docs_indexed"] = int(payload.get("docs_indexed", 0) or 0)
                stats["updated"] = stats["docs_indexed"]
                stats["skipped"] = int(payload.get("skipped", 0) or 0)
                stats["deduped"] = int(payload.get("deduped", 0) or 0)
            elif stage == "embedding_complete":
                stats["embedded"] = int(payload.get("embedded", stats.get("embedded", 0)) or 0)
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
        if job.get("frontier"):
            payload["frontier"] = dict(job.get("frontier"))
        if job.get("options"):
            payload["options"] = dict(job.get("options"))
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
            "embedding_start": 96,
            "embedding_complete": 99,
        }
        return mapping.get(stage)

    @staticmethod
    def _stage_message(stage: str, payload: dict) -> Optional[str]:
        if stage == "frontier_start":
            return "Collecting crawl seeds…"
        if stage == "frontier_complete":
            count = int(payload.get("seed_count", 0) or 0)
            domains = int(payload.get("new_domains", 0) or 0)
            if domains:
                return (
                    f"Planned {count} seed URL{'s' if count != 1 else ''} "
                    f"across {domains} domain{'s' if domains != 1 else ''}."
                )
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
        if stage == "embedding_start":
            docs = int(payload.get("docs", 0) or 0)
            return f"Embedding {docs} normalized document{'s' if docs != 1 else ''}…"
        if stage == "embedding_complete":
            embedded = int(payload.get("embedded", 0) or 0)
            return f"Embedded {embedded} document{'s' if embedded != 1 else ''}."
        return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _trigger_hot_reload(self) -> None:
        service = self._search_service
        if service is None:
            return
        try:
            service.invalidate_index()
        except AttributeError:  # pragma: no cover - legacy compatibility
            LOGGER.debug("search service does not expose invalidate_index", exc_info=True)
        except Exception:  # pragma: no cover - defensive logging only
            LOGGER.exception("failed to hot-reload search index", exc_info=True)

    def _vector_pipeline_ready(self) -> bool:
        return bool(self._vector_store and self._embedder and self._chunker)

    def _embed_documents(self, docs: Sequence[dict]) -> int:
        vector_store = self._vector_store
        embedder = self._embedder
        chunker = self._chunker
        if not vector_store or not embedder or not chunker:
            return 0
        embedded = 0
        for doc in docs:
            if not isinstance(doc, dict):
                continue
            url = (doc.get("url") or "").strip()
            body = (doc.get("body") or "").strip()
            if not url or not body:
                continue
            title = (doc.get("title") or "").strip() or url
            content_hash = hashlib.sha256(body.encode("utf-8", errors="ignore")).hexdigest()
            try:
                if hasattr(vector_store, "needs_update") and not vector_store.needs_update(url, None, content_hash):
                    continue
            except Exception:  # pragma: no cover - logging only
                LOGGER.debug("vector store needs_update failed for %s", url, exc_info=True)
            try:
                chunks = chunker.chunk_text(body)
            except Exception:  # pragma: no cover - logging only
                LOGGER.exception("failed to chunk document %s", url, exc_info=True)
                continue
            if not chunks:
                continue
            try:
                embeddings = embedder.embed_documents([chunk.text for chunk in chunks])
            except Exception:  # pragma: no cover - logging only
                LOGGER.exception("failed to embed document %s", url, exc_info=True)
                continue
            if not embeddings:
                continue
            try:
                vector_store.upsert(
                    url=url,
                    title=title,
                    etag=doc.get("etag"),
                    content_hash=content_hash,
                    chunks=chunks,
                    embeddings=embeddings,
                )
            except Exception:  # pragma: no cover - logging only
                LOGGER.exception("failed to upsert document %s", url, exc_info=True)
                continue
            embedded += 1
        return embedded

    def _prepare_frontier(
        self,
        query: str,
        *,
        budget: int,
        depth: int,
        use_llm: bool,
        model: Optional[str],
        manual_seeds: Sequence[str],
    ) -> tuple[Optional[list[Candidate]], dict]:
        manual_candidates = self._manual_seed_candidates(manual_seeds)
        if manual_candidates:
            metadata = self._seed_metadata(manual_candidates, budget=budget, depth=depth, mode="manual")
            return manual_candidates, metadata

        try:
            limit = max(budget * depth, depth * 10)
            discovered = list(
                self._discovery.discover(
                    query,
                    limit=limit,
                    use_llm=use_llm,
                    model=model,
                )
            )
        except Exception:  # pragma: no cover - defensive logging only
            LOGGER.exception("discovery engine failed for '%s'", query, exc_info=True)
            discovered = []

        if discovered:
            metadata = self._seed_metadata(discovered, budget=budget, depth=depth, mode="discovery")
            return discovered, metadata

        metadata = self._seed_metadata([], budget=budget, depth=depth, mode="discovery")
        return None, metadata

    def _manual_seed_candidates(self, seeds: Sequence[str]) -> list[Candidate]:
        candidates: list[Candidate] = []
        seen: set[str] = set()
        for seed in seeds:
            candidate = (seed or "").strip()
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            candidates.append(Candidate(url=candidate, source="manual", weight=1.25))
        return candidates

    def _seed_metadata(
        self,
        seeds: Sequence[Candidate],
        *,
        budget: int,
        depth: int,
        mode: str,
    ) -> dict:
        domains: set[str] = set()
        for candidate in seeds:
            try:
                parsed = urlparse(candidate.url)
            except Exception:
                continue
            host = (parsed.netloc or "").lower()
            if host.startswith("www."):
                host = host[4:]
            if host:
                domains.add(host)
        preview = []
        for candidate in list(seeds)[: min(len(seeds), 50)]:
            preview.append(
                {
                    "url": candidate.url,
                    "source": getattr(candidate, "source", "manual"),
                    "score": getattr(candidate, "score", None),
                    "weight": getattr(candidate, "weight", None),
                }
            )
        return {
            "mode": mode,
            "budget": budget,
            "depth": depth,
            "seed_count": len(seeds),
            "new_domains": len(domains),
            "seeds": preview,
        }

    def _effective_budget(self, requested: Optional[int]) -> int:
        numeric = self._coerce_positive_int(requested)
        if numeric is None:
            try:
                return max(1, int(self.config.focused_budget))
            except Exception:  # pragma: no cover - fallback for misconfigured budget
                return 1
        return numeric

    def _effective_depth(self, requested: Optional[int]) -> int:
        numeric = self._coerce_positive_int(requested)
        if numeric is None:
            return self._frontier_depth_default
        return max(1, numeric)

    @staticmethod
    def _coerce_positive_int(value: Optional[int]) -> Optional[int]:
        if value is None:
            return None
        try:
            numeric = int(value)
        except (TypeError, ValueError):
            return None
        return numeric if numeric > 0 else None

    @staticmethod
    def _sanitize_seeds(seeds: Optional[Sequence[str]]) -> list[str]:
        sanitized: list[str] = []
        if not seeds:
            return sanitized
        for item in seeds:
            if not isinstance(item, str):
                continue
            candidate = item.strip()
            if candidate and candidate not in sanitized:
                sanitized.append(candidate)
        return sanitized

