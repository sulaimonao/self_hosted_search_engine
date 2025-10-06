"""Background worker draining pending vectorization tasks."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Mapping, Sequence

from backend.app.db import AppStateDB
from backend.app.services.vector_index import EmbedderUnavailableError, VectorIndexService

LOGGER = logging.getLogger(__name__)


class PendingVectorWorker:
    """Polls :class:`AppStateDB` for pending documents and embeds them."""

    def __init__(
        self,
        state_db: AppStateDB,
        vector_index: VectorIndexService,
        *,
        interval: float = 5.0,
        batch_size: int = 5,
        max_backoff: float = 300.0,
    ) -> None:
        self._state_db = state_db
        self._vector_index = vector_index
        self._interval = max(1.0, float(interval))
        self._batch_size = max(1, int(batch_size))
        self._max_backoff = max(30.0, float(max_backoff))
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="pending-vector-worker", daemon=True)

    def start(self) -> None:
        if self._thread.is_alive():
            return
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                batch = self._state_db.pop_pending_documents(self._batch_size)
            except Exception:  # pragma: no cover - defensive logging
                LOGGER.exception("failed to pop pending vector documents")
                time.sleep(self._interval)
                continue

            if not batch:
                self._stop.wait(self._interval)
                continue

            for record in batch:
                doc_id = str(record.get("doc_id"))
                attempts = int(record.get("attempts") or 0)
                chunks = record.get("chunks") or []
                if not chunks:
                    LOGGER.debug("removing empty pending document %s", doc_id)
                    self._state_db.clear_pending_document(doc_id)
                    continue
                try:
                    self._vector_index.index_from_pending(
                        doc_id=doc_id,
                        title=str(record.get("title") or ""),
                        resolved_title=str(record.get("resolved_title") or record.get("title") or ""),
                        doc_hash=str(record.get("doc_hash") or ""),
                        sim_signature=record.get("sim_signature"),
                        url=str(record.get("url") or ""),
                        metadata=self._ensure_mapping(record.get("metadata")),
                        chunks=[
                            (int(chunk.get("index", idx)), str(chunk.get("text", "")), self._ensure_mapping(chunk.get("metadata")))
                            for idx, chunk in enumerate(chunks)
                        ],
                    )
                except EmbedderUnavailableError as exc:
                    backoff = min(self._max_backoff, self._interval * (2 ** attempts))
                    LOGGER.info(
                        "embedder unavailable; rescheduling pending doc %s in %.1fs (%s)",
                        doc_id,
                        backoff,
                        exc,
                    )
                    self._state_db.reschedule_pending_document(
                        doc_id,
                        delay=backoff,
                        attempts=attempts + 1,
                    )
                except Exception:  # pragma: no cover - defensive logging
                    LOGGER.exception("failed to index pending document %s", doc_id)
                    self._state_db.reschedule_pending_document(
                        doc_id,
                        delay=min(self._max_backoff, self._interval * (2 ** (attempts + 1))),
                        attempts=attempts + 1,
                    )
                else:
                    self._state_db.clear_pending_document(doc_id)

    @staticmethod
    def _ensure_mapping(value: Any) -> Mapping[str, Any]:
        if isinstance(value, Mapping):
            return value
        return {}


__all__ = ["PendingVectorWorker"]
