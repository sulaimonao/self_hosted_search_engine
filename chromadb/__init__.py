"""Lightweight stub of the ``chromadb`` package used for local development.

This implementation avoids importing the real ``chromadb`` dependency, which
is known to crash on some platforms due to native extensions. Only the minimal
surface required by ``engine.data.store.VectorStore`` is provided.
"""

from __future__ import annotations

from pathlib import Path
from threading import RLock
from typing import Any, Mapping

from .api.models.Collection import Collection
from .config import Settings


class PersistentClient:
    """Simplified persistent client that manages in-process collections."""

    def __init__(self, *, path: str | Path, settings: Settings | None = None) -> None:
        self._root = Path(path)
        self._root.mkdir(parents=True, exist_ok=True)
        self._settings = settings or Settings()
        self._collections: dict[str, Collection] = {}
        self._lock = RLock()

    def get_or_create_collection(
        self, name: str, metadata: Mapping[str, Any] | None = None
    ) -> Collection:
        key = name.strip() or "default"
        with self._lock:
            collection = self._collections.get(key)
            if collection is None:
                collection = Collection(self._root, key, metadata=metadata or {})
                self._collections[key] = collection
            return collection


__all__ = ["PersistentClient", "Settings", "Collection"]
