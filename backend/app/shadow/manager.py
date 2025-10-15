"""Shadow mode indexing orchestrator."""

from __future__ import annotations

import json
import threading
import time
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional

import trafilatura
from flask import Flask
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

from backend.app.db import AppStateDB
from backend.app.jobs.runner import JobRunner
from backend.app.services.vector_index import IndexResult, VectorIndexService
from server.json_logger import log_event

_DEFAULT_TIMEOUT_MS = 45_000
_RETRY_TIMEOUT_MS = 90_000
_SCROLL_DELAY_MS = 400
_SCROLL_STEPS = 4
_JOB_STEPS = 5
_BLOCKED_PATTERNS = [
    "*://*.doubleclick.net/*",
    "*://*.googlesyndication.com/*",
    "*://*.adservice.google.com/*",
    "*://*.facebook.net/*",
]


@dataclass(slots=True)
class ShadowJobOutcome:
    """Structured result for a completed shadow index job."""

    url: str
    title: str
    chunks: int
    pending_embedding: bool
    doc_id: str | None = None
    tokens: int | None = None
    metrics: Dict[str, float] | None = None


class ShadowIndexer:
    """Manage background Playwright fetch + indexing jobs."""

    def __init__(
        self,
        *,
        app: Flask,
        runner: JobRunner,
        vector_index: VectorIndexService,
        state_db: AppStateDB,
        enabled: bool = False,
    ) -> None:
        self._app = app
        self._runner = runner
        self._vector_index = vector_index
        self._state_db = state_db
        self._lock = threading.RLock()
        self._states: Dict[str, Dict[str, Any]] = {}
        self._job_registry: Dict[str, Dict[str, Any]] = {}
        self._recent_requests: Dict[str, tuple[str, float]] = {}
        self._url_jobs: Dict[str, str] = {}
        self._dedupe_window = 5.0
        stored_enabled = state_db.get_setting("shadow_enabled")
        if stored_enabled is not None:
            self._enabled = stored_enabled.strip().lower() in {"1", "true", "yes", "on"}
        else:
            self._enabled = bool(enabled)
        self._mode_updated_at = time.time()

    def _dedupe_key(self, url: str, tab_id: int | None) -> str:
        return f"{tab_id if tab_id is not None else 'global'}|{url}"

    def _prune_recent(self, now: float) -> None:
        expired = [key for key, (_, ts) in self._recent_requests.items() if now - ts > self._dedupe_window]
        for key in expired:
            self._recent_requests.pop(key, None)

    def _set_job_status(self, job_id: str, **patch: Any) -> Dict[str, Any]:
        with self._lock:
            current = self._job_registry.get(job_id)
            if current is None:
                current = {
                    "jobId": job_id,
                    "state": "queued",
                    "phase": "queued",
                    "message": None,
                    "etaSeconds": None,
                    "docs": [],
                    "errors": [],
                    "metrics": {},
                    "progress": None,
                }
            else:
                current = dict(current)
            metrics_patch = patch.pop("metrics", None)
            docs_patch = patch.pop("docs", None)
            errors_patch = patch.pop("errors", None)
            for key, value in patch.items():
                if value is not None or key in {"message", "etaSeconds", "reason", "pendingEmbedding"}:
                    current[key] = value
            if metrics_patch is not None:
                base_metrics = dict(current.get("metrics") or {})
                for key, value in metrics_patch.items():
                    if value is not None:
                        base_metrics[key] = value
                current["metrics"] = base_metrics
            if docs_patch is not None:
                current["docs"] = docs_patch
            if errors_patch is not None:
                current["errors"] = errors_patch
            current["updatedAt"] = time.time()
            self._job_registry[job_id] = current
            return dict(current)

    def _status_from_db(self, record: Mapping[str, Any]) -> Dict[str, Any]:
        job_id = str(record.get("job_id") or record.get("jobId") or "")
        if not job_id:
            raise ValueError("job_id_required")
        phase = str(record.get("phase") or "queued")
        steps_total = int(record.get("steps_total") or record.get("stepsTotal") or 0)
        steps_completed = int(record.get("steps_completed") or record.get("stepsCompleted") or 0)
        progress = None
        if steps_total > 0:
            progress = max(0.0, min(1.0, steps_completed / float(steps_total)))
        eta_seconds = record.get("eta_seconds") or record.get("etaSeconds")
        message = record.get("message")
        state = record.get("state")
        if not state:
            if phase in {"done", "indexed"}:
                state = "done"
            elif phase in {"error", "failed"}:
                state = "error"
            elif phase == "queued":
                state = "queued"
            else:
                state = "running"
        payload = {
            "jobId": job_id,
            "url": record.get("url"),
            "state": state,
            "phase": phase,
            "message": message,
            "etaSeconds": eta_seconds,
            "docs": [],
            "errors": [],
            "metrics": {},
            "progress": progress,
            "updatedAt": record.get("updated_at") or record.get("updatedAt"),
        }
        return payload

    def job_status(self, job_id: str) -> Dict[str, Any] | None:
        normalized = (job_id or "").strip()
        if not normalized:
            raise ValueError("job_id_required")
        with self._lock:
            snapshot = self._job_registry.get(normalized)
            if snapshot is not None:
                return dict(snapshot)
        record = self._state_db.get_job_status(normalized)
        if record:
            status = self._status_from_db(record)
            filtered = {k: v for k, v in status.items() if k != "jobId"}
            self._set_job_status(normalized, **filtered)
            status.setdefault("jobId", normalized)
            return status
        return None

    def status_by_url(self, url: str) -> Dict[str, Any]:
        normalized = self._normalize_url(url)
        if not normalized:
            raise ValueError("url_required")
        with self._lock:
            job_id = self._url_jobs.get(normalized)
        if job_id:
            status = self.job_status(job_id)
            if status is not None:
                return status
        return {
            "url": normalized,
            "state": "idle",
            "phase": "idle",
            "docs": [],
            "errors": [],
            "metrics": {},
            "jobId": None,
        }

    def enqueue(
        self, url: str, *, tab_id: int | None = None, reason: str | None = None
    ) -> Dict[str, Any]:
        normalized = self._normalize_url(url)
        if not normalized:
            raise ValueError("url_required")

        if not self.enabled:
            raise RuntimeError("shadow_disabled")

        now = time.time()
        key = self._dedupe_key(normalized, tab_id)
        with self._lock:
            self._prune_recent(now)
            existing_recent = self._recent_requests.get(key)
            if existing_recent:
                job_id, ts = existing_recent
                if now - ts < self._dedupe_window:
                    snapshot = self._job_registry.get(job_id)
                    if snapshot is not None:
                        return dict(snapshot)
            existing = self._states.get(normalized)
            if existing and existing.get("state") in {"queued", "running"}:
                job_id = existing.get("job_id") or existing.get("jobId")
                if job_id:
                    snapshot = self._job_registry.get(str(job_id))
                    if snapshot is not None:
                        self._recent_requests[key] = (str(job_id), now)
                        return dict(snapshot)
                return dict(existing)

        job_id_holder: Dict[str, str] = {}

        def task(
            job_url: str = normalized, job_ref: Dict[str, str] = job_id_holder
        ) -> None:
            job_id = job_ref.get("id", "")
            self._run_job(job_url, job_id)

        job_id = self._runner.submit(task)
        job_id_holder["id"] = job_id

        queued_state = self._set_job_status(
            job_id,
            url=normalized,
            state="queued",
            phase="queued",
            message="Queued for shadow indexing",
            etaSeconds=None,
            docs=[],
            errors=[],
            metrics={},
            progress=0.0,
            reason=reason,
        )
        queued_state["tabId"] = tab_id

        with self._lock:
            self._states[normalized] = {
                "url": normalized,
                "state": "queued",
                "job_id": job_id,
                "jobId": job_id,
                "updated_at": queued_state.get("updatedAt"),
                "updatedAt": queued_state.get("updatedAt"),
                "phase": "queued",
                "tabId": tab_id,
            }
            self._url_jobs[normalized] = job_id
            self._recent_requests[key] = (job_id, now)

        self._update_job_status(
            job_id,
            url=normalized,
            phase="queued",
            message="Queued for shadow indexing",
            step=0,
            started_at=queued_state.get("updatedAt"),
        )

        return dict(queued_state)

    def status(self, url: str) -> Dict[str, Any]:
        return self.status_by_url(url)

    @property
    def enabled(self) -> bool:
        with self._lock:
            return self._enabled

    def set_enabled(self, enabled: bool) -> Dict[str, Any]:
        with self._lock:
            self._enabled = bool(enabled)
            self._mode_updated_at = time.time()
            self._state_db.set_setting(
                "shadow_enabled", "true" if self._enabled else "false"
            )
        return self.get_config()

    def toggle(self) -> Dict[str, Any]:
        with self._lock:
            self._enabled = not self._enabled
            self._mode_updated_at = time.time()
            self._state_db.set_setting(
                "shadow_enabled", "true" if self._enabled else "false"
            )
        return self.get_config()

    def get_config(self) -> Dict[str, Any]:
        with self._lock:
            queued = 0
            running = 0
            latest: Optional[Dict[str, Any]] = None
            latest_ts = 0.0
            for state in self._states.values():
                status = state.get("state")
                if status == "queued":
                    queued += 1
                elif status == "running":
                    running += 1
                updated_at = state.get("updated_at")
                try:
                    ts = float(updated_at) if updated_at is not None else 0.0
                except (TypeError, ValueError):
                    ts = 0.0
                if ts >= latest_ts:
                    latest_ts = ts
                    latest = state

            payload: Dict[str, Any] = {
                "enabled": self._enabled,
                "queued": queued,
                "running": running,
                "updated_at": self._mode_updated_at,
            }
            if latest:
                payload["last_url"] = latest.get("url")
                payload["last_state"] = latest.get("state")
                if "updated_at" in latest:
                    payload["last_updated_at"] = latest.get("updated_at")
            return payload

    def _persist_state(self) -> None:
        # retained for backwards compatibility; persistence handled in set_enabled
        self._state_db.set_setting("shadow_enabled", "true" if self._enabled else "false")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _run_job(self, url: str, job_id: str) -> ShadowJobOutcome | None:
        with self._app.app_context():
            self._transition(url, {"state": "running", "job_id": job_id})
            self._update_job_status(
                job_id,
                url=url,
                phase="fetching",
                message="Fetching URL",
                step=1,
            )
            log_event("INFO", "shadow.start", url=url, job_id=job_id)
            try:
                outcome = self._fetch_and_index(url, job_id)
            except (PlaywrightTimeout, PlaywrightError) as exc:
                message = str(exc)
                self._transition(
                    url,
                    {
                        "state": "error",
                        "job_id": job_id,
                        "error": message,
                        "error_kind": exc.__class__.__name__,
                    },
                )
                log_event(
                    "ERROR",
                    "shadow.fetch_failed",
                    url=url,
                    job_id=job_id,
                    error=exc.__class__.__name__,
                    msg=message,
                )
                self._update_job_status(
                    job_id,
                    url=url,
                    phase="failed",
                    message=message,
                    step=_JOB_STEPS,
                    retries=1,
                )
                raise
            except Exception as exc:  # pragma: no cover - defensive fallback
                message = str(exc)
                self._transition(
                    url,
                    {
                        "state": "error",
                        "job_id": job_id,
                        "error": message,
                        "error_kind": exc.__class__.__name__,
                    },
                )
                log_event(
                    "ERROR",
                    "shadow.error",
                    url=url,
                    job_id=job_id,
                    error=exc.__class__.__name__,
                    msg=message,
                )
                self._update_job_status(
                    job_id,
                    url=url,
                    phase="failed",
                    message=message,
                    step=_JOB_STEPS,
                )
                raise

            payload = {
                "url": url,
                "state": "done",
                "job_id": job_id,
                "title": outcome.title,
                "chunks": outcome.chunks,
                "pending_embedding": outcome.pending_embedding,
                "updated_at": time.time(),
            }
            payload["jobId"] = job_id
            payload["updatedAt"] = payload["updated_at"]
            self._transition(url, payload)
            log_event(
                "INFO",
                "shadow.indexed",
                url=url,
                job_id=job_id,
                title=outcome.title,
                chunks=outcome.chunks,
                pending=outcome.pending_embedding,
            )
            return outcome

    def _transition(self, url: str, patch: Dict[str, Any]) -> Dict[str, Any]:
        normalized = self._normalize_url(url)
        if not normalized:
            return {"url": url, "state": "idle"}
        with self._lock:
            state = dict(self._states.get(normalized, {"url": normalized}))
            state.update(patch)
            timestamp = time.time()
            state["updated_at"] = timestamp
            state["updatedAt"] = timestamp
            job_identifier = state.get("job_id") or state.get("jobId")
            if job_identifier:
                job_id = str(job_identifier)
                state["jobId"] = job_id
                self._url_jobs[normalized] = job_id
                message = state.get("status_message") or state.get("message")
                job_patch = {
                    "url": normalized,
                    "state": state.get("state"),
                    "phase": state.get("phase"),
                    "message": message,
                    "pendingEmbedding": state.get("pending_embedding"),
                }
                filtered = {k: v for k, v in job_patch.items() if v is not None}
                if filtered:
                    self._set_job_status(job_id, **filtered)
            self._states[normalized] = state
            return dict(state)

    def _update_job_status(
        self,
        job_id: str,
        *,
        url: str,
        phase: str,
        message: str,
        step: int,
        steps_total: int = _JOB_STEPS,
        retries: int = 0,
        eta_seconds: float | None = None,
        started_at: float | None = None,
    ) -> None:
        steps_completed = max(0, min(int(step), int(steps_total)))
        self._state_db.upsert_job_status(
            job_id,
            url=url,
            phase=phase,
            steps_total=int(steps_total),
            steps_completed=steps_completed,
            retries=int(retries),
            eta_seconds=eta_seconds,
            message=message,
            started_at=started_at,
        )
        progress = None
        if steps_total > 0:
            progress = max(0.0, min(1.0, steps_completed / float(steps_total)))
        if phase in {"queued"}:
            state = "queued"
        elif phase in {"indexed", "done"}:
            state = "done"
        elif phase in {"failed", "error"}:
            state = "error"
        else:
            state = "running"
        self._set_job_status(
            job_id,
            url=url,
            phase=phase,
            message=message,
            state=state,
            etaSeconds=eta_seconds,
            progress=progress,
            retries=retries,
        )
        self._transition(url, {"phase": phase, "status_message": message, "job_id": job_id})

    def _fetch_and_index(self, url: str, job_id: str) -> ShadowJobOutcome:
        title, text, metadata, timing = self._fetch_with_playwright(url)
        self._set_job_status(
            job_id,
            metrics={
                "fetch_ms": timing.get("fetch_ms"),
                "extract_ms": timing.get("extract_ms"),
            },
        )
        self._update_job_status(
            job_id,
            url=url,
            phase="extracted",
            message="Extracted page content",
            step=2,
        )
        cleaned_title = title.strip() if title.strip() else url
        metadata = dict(metadata)
        metadata.setdefault("source", "shadow_mode")
        self._update_job_status(
            job_id,
            url=url,
            phase="embedding",
            message="Indexing document",
            step=3,
        )
        embed_start = time.time()
        index_result: IndexResult = self._vector_index.upsert_document(
            text=text,
            url=url,
            title=cleaned_title,
            metadata=metadata,
        )
        embed_ms = (time.time() - embed_start) * 1000.0
        tokens = len(text.split()) if text else 0
        metrics = {
            "fetch_ms": timing.get("fetch_ms"),
            "extract_ms": timing.get("extract_ms"),
            "embed_ms": embed_ms,
            "index_ms": embed_ms,
        }
        docs_payload = [
            {"id": index_result.doc_id, "title": cleaned_title, "tokens": tokens}
        ]
        self._set_job_status(
            job_id,
            metrics=metrics,
            docs=docs_payload,
            title=cleaned_title,
            chunks=index_result.chunks,
            pendingEmbedding=index_result.pending_embedding,
        )
        if index_result.pending_embedding:
            self._update_job_status(
                job_id,
                url=url,
                phase="warming_up",
                message="Embedding model warming up",
                step=4,
            )
        else:
            message = (
                f"Indexed {index_result.chunks} chunk(s)"
                if index_result.chunks
                else "No new chunks (duplicate or empty)"
            )
            self._update_job_status(
                job_id,
                url=url,
                phase="indexed",
                message=message,
                step=_JOB_STEPS,
            )
        return ShadowJobOutcome(
            url=url,
            title=cleaned_title,
            chunks=index_result.chunks,
            pending_embedding=index_result.pending_embedding,
            doc_id=index_result.doc_id,
            tokens=tokens,
            metrics=metrics,
        )

    def _fetch_with_playwright(self, url: str) -> tuple[str, str, Dict[str, Any], Dict[str, float]]:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(ignore_https_errors=True)
            page = context.new_page()
            page.set_default_navigation_timeout(_RETRY_TIMEOUT_MS)
            page.set_default_timeout(_RETRY_TIMEOUT_MS)
            for pattern in _BLOCKED_PATTERNS:
                page.route(pattern, lambda route, _pattern=pattern: route.abort())

            page_title = url
            text = ""
            metadata: Dict[str, Any] = {}
            lang_value: Any = None
            fetch_start = time.time()
            fetch_ms = 0.0
            extract_ms = 0.0

            try:
                navigation_attempts = [
                    ("networkidle", _RETRY_TIMEOUT_MS),
                    ("domcontentloaded", 120_000),
                ]
                last_error: Exception | None = None
                for wait_until, timeout in navigation_attempts:
                    try:
                        page.goto(url, wait_until=wait_until, timeout=timeout)
                        last_error = None
                        break
                    except PlaywrightTimeout as exc:
                        last_error = exc
                        continue
                if last_error is not None:
                    raise last_error
                for _ in range(_SCROLL_STEPS):
                    page.wait_for_timeout(_SCROLL_DELAY_MS)
                    with suppress(Exception):
                        page.mouse.wheel(0, 800)
                page.wait_for_timeout(_SCROLL_DELAY_MS)
                html = page.content()
                fetch_ms = (time.time() - fetch_start) * 1000.0
                page_title = page.title() or url
                lang_value = page.evaluate("document.documentElement?.lang || null")
                extract_start = time.time()
                text, metadata = self._extract_text(html)
                extract_ms = (time.time() - extract_start) * 1000.0
                if not text.strip():
                    fallback = page.evaluate("document.body ? document.body.innerText : ''")
                    if isinstance(fallback, str):
                        text = fallback
            finally:
                with suppress(Exception):
                    context.close()
                with suppress(Exception):
                    browser.close()

        normalized_metadata: Dict[str, Any] = {}
        if metadata:
            normalized_metadata.update(metadata)
        if isinstance(lang_value, str) and lang_value.strip():
            normalized_metadata.setdefault("lang", lang_value.strip())
        if not text.strip():
            raise RuntimeError("shadow_empty_text")
        metrics = {"fetch_ms": fetch_ms, "extract_ms": extract_ms}
        return page_title, text, normalized_metadata, metrics

    def _extract_text(self, html: str) -> tuple[str, Dict[str, Any]]:
        metadata: Dict[str, Any] = {}
        with suppress(Exception):
            raw = trafilatura.extract(
                html,
                include_comments=False,
                include_tables=False,
                include_images=False,
                output_format="json",
            )
            if raw:
                data = json.loads(raw)
                text_value = data.get("text") if isinstance(data, dict) else ""
                if isinstance(text_value, str) and text_value.strip():
                    metadata = {
                        key: value
                        for key, value in data.items()
                        if key in {"title", "lang", "description"}
                    }
                    return text_value, metadata
        text = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=False,
            include_images=False,
        )
        if isinstance(text, str):
            return text, metadata
        return "", metadata

    @staticmethod
    def _normalize_url(url: str) -> str:
        return url.strip()


__all__ = ["ShadowIndexer"]
