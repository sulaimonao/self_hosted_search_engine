"""Local filesystem discovery service."""

from __future__ import annotations

import json
import logging
import queue
from collections import deque
import threading
import time
import uuid
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from bs4 import BeautifulSoup
from pdfminer.high_level import extract_text as pdf_extract_text
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer


LOGGER = logging.getLogger(__name__)


def _safe_log(level: str, msg: str, *args, **kwargs) -> None:
    """Log safely from background threads. If the configured logging
    handlers have been closed (pytest capture or shutdown), swallowing
    the error is preferable to crashing worker threads.
    """
    # Attempt to emit the record but avoid logging internals printing
    # exceptions to stderr (logging.raiseExceptions) which can trigger
    # writes to closed streams. We temporarily disable raiseExceptions
    # and then restore it.
    try:
        prev = logging.raiseExceptions
        logging.raiseExceptions = False
        try:
            getattr(LOGGER, level)(msg, *args, **kwargs)
        except Exception:
            # Swallow any exceptions from logging emitters to keep
            # background threads alive.
            return
    finally:
        try:
            logging.raiseExceptions = prev
        except Exception:
            # Best-effort restore; ignore on failure.
            pass


SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".txt",
    ".md",
    ".markdown",
    ".html",
    ".htm",
}

MAX_TEXT_LENGTH = 750_000
PREVIEW_LENGTH = 400

LOG_SAMPLE_WINDOW_SECONDS = 30.0
LOG_SAMPLE_LIMIT = 8


@dataclass(slots=True)
class DiscoveryRecord:
    """In-memory representation of a discovered document."""

    id: str
    path: str
    name: str
    ext: str
    size: int
    mtime: float
    created_at: float
    text: str
    preview: str


class _DirectoryEventHandler(FileSystemEventHandler):
    """Watchdog handler that forwards file events to the service."""

    def __init__(self, service: "LocalDiscoveryService") -> None:
        self._service = service

    def on_created(
        self, event: FileSystemEvent
    ) -> None:  # pragma: no cover - watchdog glue
        if event.is_directory:
            return
        self._service.enqueue(Path(event.src_path))

    def on_modified(
        self, event: FileSystemEvent
    ) -> None:  # pragma: no cover - watchdog glue
        if event.is_directory:
            return
        self._service.enqueue(Path(event.src_path))

    def on_moved(
        self, event: FileSystemEvent
    ) -> None:  # pragma: no cover - watchdog glue
        if event.is_directory:
            return
        self._service.enqueue(Path(event.dest_path))


class LocalDiscoveryService:
    """Monitor local directories for newly downloaded documents."""

    def __init__(self, directories: Iterable[Path], ledger_path: Path) -> None:
        self._directories = [directory.resolve() for directory in directories]
        self._ledger_path = ledger_path
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="local-discovery"
        )
        # typing the Observer here causes some linters/typecheckers to
        # complain depending on environment; keep it unannotated.
        self._observer = None
        # Use plain assignments here to avoid environments that reject
        # inline variable annotations inside methods.
        self._pending = {}
        self._archive = {}
        self._subscribers = {}
        self._confirmations = {}
        self._confirmed_ids = set()
        self._seen_mtimes = {}
        self._started = False
        self._inflight_paths: set[str] = set()
        self._log_emissions: deque[float] = deque()
        self._suppressed_logs = 0
        self._load_confirmations()

    # ------------------------------------------------------------------
    # Lifecycle management
    # ------------------------------------------------------------------
    def start(self) -> None:
        """Start watchdog observers (idempotent)."""

        with self._lock:
            if self._started:
                return
            self._started = True

        for directory in self._directories:
            directory.mkdir(parents=True, exist_ok=True)

        observer = Observer()
        handler = _DirectoryEventHandler(self)
        for directory in self._directories:
            observer.schedule(handler, str(directory), recursive=False)
            LOGGER.debug("Local discovery watching %s", directory)

        observer.start()
        self._observer = observer

        # Scan existing files once to surface any pending documents.
        for directory in self._directories:
            self.scan(directory)

    def stop(self) -> None:
        """Stop observers and worker threads."""

        with self._lock:
            self._started = False

        if self._observer is not None:
            try:
                self._observer.stop()
                self._observer.join(timeout=5)
            except Exception:  # pragma: no cover - defensive shutdown
                _safe_log("exception", "Failed to stop local discovery observer")
            finally:
                self._observer = None

        self._executor.shutdown(wait=False, cancel_futures=True)

        for subscriber_id in list(self._subscribers):
            self.unsubscribe(subscriber_id)

        self._emit_suppressed_summary(force=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def enqueue(self, path: Path) -> None:
        """Schedule *path* for processing."""

        resolved = path.resolve()
        if not resolved.exists():
            return
        key = str(resolved)
        with self._lock:
            if key in self._inflight_paths:
                return
            self._inflight_paths.add(key)
        self._executor.submit(self._process_with_retries, resolved)

    def scan(self, directory: Path) -> None:
        """Eagerly scan *directory* for supported files."""

        try:
            entries = list(directory.iterdir())
        except OSError:
            return

        for entry in entries:
            if entry.is_file():
                self.enqueue(entry)

    def subscribe(self) -> tuple[str, queue.Queue[DiscoveryRecord | None]]:
        """Register an SSE subscriber."""

        token = uuid.uuid4().hex
        stream: queue.Queue[DiscoveryRecord | None] = queue.Queue()
        with self._lock:
            self._subscribers[token] = stream
            for record in self._pending.values():
                stream.put(record)
        return token, stream

    def unsubscribe(self, token: str) -> None:
        with self._lock:
            stream = self._subscribers.pop(token, None)
        if stream is not None:
            stream.put(None)

    def list_pending(self) -> list[DiscoveryRecord]:
        with self._lock:
            return list(self._pending.values())

    def get(self, record_id: str) -> Optional[DiscoveryRecord]:
        with self._lock:
            record = self._pending.get(record_id) or self._archive.get(record_id)
        return record

    def confirm(self, record_id: str, *, action: str = "included") -> bool:
        """Mark *record_id* as handled."""

        normalized = action.strip().lower() or "included"
        with self._lock:
            if record_id in self._confirmed_ids:
                return True
            record = self._pending.pop(record_id, None)
            if record is None:
                record = self._archive.get(record_id)
            if record is None:
                return False
            self._archive[record_id] = record
            self._confirmed_ids.add(record_id)
            self._confirmations[record.path] = {
                "mtime": record.mtime,
                "action": normalized,
                "confirmed_at": time.time(),
            }
            self._save_confirmations()
        return True

    def to_dict(self, record: DiscoveryRecord, *, include_text: bool) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": record.id,
            "path": record.path,
            "name": record.name,
            "ext": record.ext,
            "size": record.size,
            "mtime": record.mtime,
            "createdAt": record.created_at,
            "preview": record.preview,
        }
        if include_text:
            payload["text"] = record.text
        return payload

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _process_with_retries(self, path: Path) -> None:
        key = str(path)
        time.sleep(0.5)
        try:
            for attempt in range(3):
                try:
                    processed = self._process_path(path)
                except Exception:  # pragma: no cover - logged
                    _safe_log("exception", "Local discovery failed for %s", path)
                    return
                if processed:
                    return
                time.sleep(0.5)
        finally:
            with self._lock:
                self._inflight_paths.discard(key)

    def _process_path(self, path: Path) -> bool:
        if not path.exists():
            return False
        ext = path.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            return False

        try:
            stat = path.stat()
        except OSError:
            return False

        path_str = str(path)
        mtime = stat.st_mtime

        with self._lock:
            confirmation = self._confirmations.get(path_str)
            if confirmation:
                action = str(confirmation.get("action", "included")).strip().lower()
                if action != "retry":
                    self._seen_mtimes[path_str] = mtime
                    return False
                if float(confirmation.get("mtime", 0)) >= mtime:
                    return False
            seen = self._seen_mtimes.get(path_str)
            if seen and seen >= mtime:
                return False
            for record in self._pending.values():
                if record.path == path_str:
                    return False

        text = self._extract_text(path, ext)
        if not text:
            return False

        trimmed = text[:MAX_TEXT_LENGTH]
        preview = trimmed[:PREVIEW_LENGTH].strip()

        record = DiscoveryRecord(
            id=self._make_record_id(path_str, mtime),
            path=path_str,
            name=path.name,
            ext=ext.lstrip("."),
            size=stat.st_size,
            mtime=mtime,
            created_at=time.time(),
            text=trimmed,
            preview=preview,
        )

        with self._lock:
            self._pending[record.id] = record
            self._archive[record.id] = record
            self._seen_mtimes[path_str] = mtime
            subscribers = list(self._subscribers.values())

        for stream in subscribers:
            stream.put(record)

        if self._should_log_discovery():
            _safe_log("info", "Discovered local file: %s", path_str)
        return True

    def _extract_text(self, path: Path, ext: str) -> str:
        try:
            if ext in {".txt", ".md", ".markdown"}:
                return path.read_text(encoding="utf-8", errors="ignore")
            if ext in {".html", ".htm"}:
                raw = path.read_text(encoding="utf-8", errors="ignore")
                soup = BeautifulSoup(raw, "html.parser")
                for tag in soup(["script", "style", "noscript"]):
                    tag.decompose()
                text = soup.get_text("\n")
                return text
            if ext == ".pdf":
                return pdf_extract_text(str(path))
        except Exception:  # pragma: no cover - logged by caller
            raise
        return ""

    def _make_record_id(self, path: str, mtime: float) -> str:
        return uuid.uuid5(uuid.NAMESPACE_URL, f"{path}:{mtime}").hex

    def _load_confirmations(self) -> None:
        try:
            raw = self._ledger_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return
        except OSError:  # pragma: no cover - defensive
            _safe_log("exception", "Unable to read local discovery ledger")
            return

        try:
            payload = json.loads(raw)
        except ValueError:  # pragma: no cover - defensive
            _safe_log(
                "warning",
                "Invalid JSON in local discovery ledger: %s",
                self._ledger_path,
            )
            return

        if not isinstance(payload, dict):
            return

        entries = payload.get("paths")
        if not isinstance(entries, dict):
            return

        for path_str, entry in entries.items():
            if not isinstance(path_str, str) or not isinstance(entry, dict):
                continue
            mtime = float(entry.get("mtime", 0))
            action = str(entry.get("action", "included"))
            confirmed_at = float(entry.get("confirmed_at", time.time()))
            self._confirmations[path_str] = {
                "mtime": mtime,
                "action": action,
                "confirmed_at": confirmed_at,
            }

    def _save_confirmations(self) -> None:
        data = {"paths": self._confirmations}
        self._ledger_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._ledger_path.with_suffix(".tmp")
        tmp_path.write_text(
            json.dumps(data, indent=2, sort_keys=True), encoding="utf-8"
        )
        tmp_path.replace(self._ledger_path)

    def _should_log_discovery(self) -> bool:
        now = time.time()
        with self._lock:
            window = self._log_emissions
            while window and now - window[0] > LOG_SAMPLE_WINDOW_SECONDS:
                window.popleft()
                if not window and self._suppressed_logs:
                    _safe_log(
                        "info",
                        "Suppressed %d local discovery events in the last %.0f seconds",
                        self._suppressed_logs,
                        LOG_SAMPLE_WINDOW_SECONDS,
                    )
                    self._suppressed_logs = 0
            if len(window) >= LOG_SAMPLE_LIMIT:
                self._suppressed_logs += 1
                return False
            window.append(now)
            return True

    def _emit_suppressed_summary(self, *, force: bool = False) -> None:
        with self._lock:
            if (force or not self._log_emissions) and self._suppressed_logs:
                _safe_log(
                    "info",
                    "Suppressed %d local discovery events in the last %.0f seconds",
                    self._suppressed_logs,
                    LOG_SAMPLE_WINDOW_SECONDS,
                )
                self._suppressed_logs = 0
            if force:
                self._log_emissions.clear()


__all__ = ["LocalDiscoveryService", "DiscoveryRecord"]
