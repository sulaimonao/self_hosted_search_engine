"""Focused crawl supervisor handling background runs."""

from __future__ import annotations

import json
import logging
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from ..config import AppConfig
from ..pipeline.normalize import normalize
from ..indexer.incremental import incremental_index

LOGGER = logging.getLogger(__name__)


@dataclass
class _Job:
    query: str
    process: subprocess.Popen[str]
    log_handle: object
    started_at: float


class FocusedCrawlSupervisor:
    """Manage focused crawl subprocesses and downstream indexing."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._lock = threading.Lock()
        self._current: Optional[_Job] = None
        self._history_path = self.config.crawl_raw_dir / "focused_history.json"
        self._history: Dict[str, float] = self._load_history()

    def _load_history(self) -> Dict[str, float]:
        if not self._history_path.exists():
            return {}
        try:
            data = json.loads(self._history_path.read_text("utf-8"))
        except Exception:
            return {}
        return {str(k): float(v) for k, v in data.items() if isinstance(k, str)}

    def _persist_history(self) -> None:
        try:
            self._history_path.write_text(json.dumps(self._history, indent=2, sort_keys=True), encoding="utf-8")
        except Exception as exc:
            LOGGER.debug("unable to persist focused crawl history: %s", exc)

    def schedule(self, query: str, use_llm: bool, model: Optional[str]) -> bool:
        q = (query or "").strip()
        if not q:
            return False
        if not self.config.focused_enabled:
            LOGGER.debug("focused crawl disabled; skipping schedule for '%s'", q)
            return False
        now = time.time()
        cooldown = self.config.smart_trigger_cooldown
        with self._lock:
            if cooldown > 0:
                last = self._history.get(q)
                if last and (now - last) < cooldown:
                    LOGGER.info("cooldown active for query '%s'", q)
                    return False
            if self._current and self._current.process.poll() is None:
                LOGGER.info("focused crawl already running; skipping new schedule")
                return False
            cmd = [
                sys.executable,
                "-m",
                "crawler.run",
                f"--query={q}",
                f"--budget={self.config.focused_budget}",
                f"--out={self.config.crawl_raw_dir}",
            ]
            if use_llm:
                cmd.append("--use-llm")
            if model:
                cmd.append(f"--model={model}")
            log_handle = self.config.focused_log_path.open("a", encoding="utf-8")
            process = subprocess.Popen(  # noqa: S603
                cmd,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                text=True,
            )
            job = _Job(query=q, process=process, log_handle=log_handle, started_at=now)
            self._current = job
            self._history[q] = now
            self._persist_history()
            threading.Thread(target=self._watch_job, args=(job,), daemon=True).start()
            LOGGER.info("scheduled focused crawl for query '%s'", q)
            return True

    def _watch_job(self, job: _Job) -> None:
        code = job.process.wait()
        try:
            job.log_handle.close()
        except Exception:
            pass
        LOGGER.info("focused crawl for '%s' exited with %s", job.query, code)
        if code == 0:
            try:
                normalized = normalize(self.config.crawl_raw_dir, self.config.normalized_path)
                incremental_index(
                    self.config.index_dir,
                    self.config.ledger_path,
                    self.config.simhash_path,
                    self.config.last_index_time_path,
                    normalized,
                )
            except Exception as exc:
                LOGGER.exception("post-crawl pipeline failed: %s", exc)
        with self._lock:
            if self._current is job:
                self._current = None

    def tail_log(self, lines: int = 50) -> List[str]:
        path = self.config.focused_log_path
        if not path.exists():
            return []
        tail: deque[str] = deque(maxlen=lines)
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                tail.append(line.rstrip())
        return list(tail)

    def is_running(self) -> bool:
        with self._lock:
            if self._current and self._current.process.poll() is None:
                return True
        return False

    def last_index_time(self) -> int:
        if not self.config.last_index_time_path.exists():
            return 0
        try:
            return int(self.config.last_index_time_path.read_text("utf-8").strip() or 0)
        except Exception:
            return 0
