"""Shadow mode indexing orchestrator."""

from __future__ import annotations

import threading
import time
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, Dict, Optional

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
        stored_enabled = state_db.get_setting("shadow_enabled")
        if stored_enabled is not None:
            self._enabled = stored_enabled.strip().lower() in {"1", "true", "yes", "on"}
        else:
            self._enabled = bool(enabled)
        self._mode_updated_at = time.time()
        if stored_enabled is None:
            state_db.set_setting("shadow_enabled", "true" if self._enabled else "false")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def enqueue(self, url: str) -> Dict[str, Any]:
        normalized = self._normalize_url(url)
        if not normalized:
            raise ValueError("url_required")

        if not self.enabled:
            raise RuntimeError("shadow_disabled")

        with self._lock:
            existing = self._states.get(normalized)
            if existing and existing.get("state") in {"queued", "running"}:
                return dict(existing)

        job_id_holder: Dict[str, str] = {}

        def task(
            job_url: str = normalized, job_ref: Dict[str, str] = job_id_holder
        ) -> None:
            job_id = job_ref.get("id", "")
            self._run_job(job_url, job_id)

        job_id = self._runner.submit(task)
        job_id_holder["id"] = job_id

        state = {
            "url": normalized,
            "state": "queued",
            "job_id": job_id,
            "updated_at": time.time(),
            "phase": "queued",
        }
        state["jobId"] = job_id
        state["updatedAt"] = state["updated_at"]

        with self._lock:
            self._states[normalized] = state

        self._update_job_status(
            job_id,
            url=normalized,
            phase="queued",
            message="Queued for shadow indexing",
            step=0,
            started_at=state["updated_at"],
        )

        return dict(state)

    def status(self, url: str) -> Dict[str, Any]:
        normalized = self._normalize_url(url)
        if not normalized:
            raise ValueError("url_required")
        with self._lock:
            state = self._states.get(normalized)
            if state:
                return dict(state)
        return {"url": normalized, "state": "idle"}

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
            state.setdefault("updated_at", timestamp)
            state["updated_at"] = timestamp
            state["updatedAt"] = state["updated_at"]
            if "job_id" in state:
                state["jobId"] = state["job_id"]
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
        self._transition(url, {"phase": phase, "status_message": message, "job_id": job_id})

    def _fetch_and_index(self, url: str, job_id: str) -> ShadowJobOutcome:
        title, text, metadata = self._fetch_with_playwright(url)
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
        index_result: IndexResult = self._vector_index.upsert_document(
            text=text,
            url=url,
            title=cleaned_title,
            metadata=metadata,
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
        )

    def _fetch_with_playwright(self, url: str) -> tuple[str, str, Dict[str, Any]]:
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
                page_title = page.title() or url
                lang_value = page.evaluate("document.documentElement?.lang || null")
                text, metadata = self._extract_text(html)
                if not text.strip():
                    fallback = page.evaluate(
                        "document.body ? document.body.innerText : ''"
                    )
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
        return page_title, text, normalized_metadata

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
