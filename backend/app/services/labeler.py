"""Deferred document labeling using lightweight heuristics or LLM calls."""

from __future__ import annotations

import threading

from backend.app.db import AppStateDB


class LabelWorker(threading.Thread):
    """Background worker that assigns descriptive labels to documents."""

    def __init__(self, state_db: AppStateDB, *, interval: float = 900.0) -> None:
        super().__init__(name="label-worker", daemon=True)
        self._state_db = state_db
        self._interval = max(5.0, float(interval))
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:  # pragma: no cover - background thread exercised in integration tests
        while not self._stop.is_set():
            docs = self._state_db.fetch_documents_for_labeling(limit=10)
            if not docs:
                self._stop.wait(self._interval)
                continue
            for doc in docs:
                labels = self._label_document(doc)
                if labels:
                    self._state_db.update_document_labels(doc["id"], labels)
            self._stop.wait(self._interval)

    def _label_document(self, doc: dict) -> list[str]:
        title = (doc.get("title") or "").lower()
        description = (doc.get("description") or "").lower()
        text = f"{title} {description}".strip()
        labels: list[str] = []
        if not text:
            return labels
        if any(keyword in text for keyword in ("tutorial", "guide", "how to")):
            labels.append("tutorial")
        if any(keyword in text for keyword in ("release", "changelog", "version")):
            labels.append("release")
        if any(keyword in text for keyword in ("research", "paper", "study")):
            labels.append("research")
        if "api" in text:
            labels.append("api")
        if not labels:
            labels.append("general")
        return sorted(set(labels))


class MemoryAgingWorker(threading.Thread):
    """Background worker that periodically decays memory strength."""

    def __init__(self, state_db: AppStateDB, *, interval: float = 86_400.0, decay: float = 0.9) -> None:
        super().__init__(name="memory-aging-worker", daemon=True)
        self._state_db = state_db
        self._interval = max(60.0, float(interval))
        self._decay = decay
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:  # pragma: no cover - background thread exercised in integration tests
        while not self._stop.is_set():
            self._state_db.age_memories(decay=self._decay)
            self._stop.wait(self._interval)


__all__ = ["LabelWorker", "MemoryAgingWorker"]
