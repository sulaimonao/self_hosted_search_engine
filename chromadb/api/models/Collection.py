"""Subset of the ChromaDB collection API for local development."""

from __future__ import annotations

import json
import os
from pathlib import Path
from threading import RLock
from typing import Any, Mapping, Sequence

import math


class Collection:
    """Persist collection items on disk and provide cosine similarity queries."""

    def __init__(
        self,
        root: Path,
        name: str,
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        self._root = Path(root)
        self._name = name
        self._metadata = dict(metadata or {})
        self._path = self._root / f"{name}.json"
        self._lock = RLock()
        self._entries: list[dict[str, Any]] = []
        self._load()

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------
    def _load(self) -> None:
        if not self._path.exists():
            self._entries = []
            return
        try:
            with self._path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, ValueError):
            payload = {}
        entries = payload.get("entries")
        if isinstance(entries, list):
            cleaned: list[dict[str, Any]] = []
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                identifier = entry.get("id")
                embedding = entry.get("embedding")
                if identifier is None or embedding is None:
                    continue
                cleaned.append(entry)
            self._entries = cleaned
        else:
            self._entries = []

    def _persist(self) -> None:
        tmp_path = self._path.with_suffix(".json.tmp")
        payload = {"entries": self._entries, "metadata": self._metadata}
        self._root.mkdir(parents=True, exist_ok=True)
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False)
        os.replace(tmp_path, self._path)

    # ------------------------------------------------------------------
    # Utility helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _normalise_where(where: Mapping[str, Any] | None) -> list[Mapping[str, Any]]:
        if not where:
            return []
        clauses: list[Mapping[str, Any]] = []
        if "$and" in where and isinstance(where["$and"], Sequence):
            for clause in where["$and"]:
                if isinstance(clause, Mapping):
                    clauses.append(dict(clause))
        elif isinstance(where, Mapping):
            clauses.append(dict(where))
        return clauses

    @staticmethod
    def _entry_matches(
        entry: Mapping[str, Any], clauses: Sequence[Mapping[str, Any]]
    ) -> bool:
        if not clauses:
            return True
        metadata = entry.get("metadata")
        if not isinstance(metadata, Mapping):
            return False
        for clause in clauses:
            match = True
            for key, value in clause.items():
                if metadata.get(key) != value:
                    match = False
                    break
            if match:
                return True
        return False

    def _filtered_entries(
        self,
        where: Mapping[str, Any] | None,
    ) -> list[dict[str, Any]]:
        clauses = self._normalise_where(where)
        return [entry for entry in self._entries if self._entry_matches(entry, clauses)]

    @staticmethod
    def _to_vector(embedding: Sequence[float]) -> list[float]:
        values = list(embedding)
        if any(isinstance(value, (list, tuple)) for value in values):
            raise ValueError("embedding must be a 1D sequence")
        return [float(value) for value in values]

    @staticmethod
    def _dot(a: Sequence[float], b: Sequence[float]) -> float:
        return sum(x * y for x, y in zip(a, b))

    @staticmethod
    def _norm(vec: Sequence[float]) -> float:
        return math.sqrt(sum(x * x for x in vec))

    def _cosine(self, a: Sequence[float], b: Sequence[float]) -> float:
        denom = self._norm(a) * self._norm(b)
        if denom <= 1e-12:
            return 0.0
        return self._dot(a, b) / denom

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def delete(self, where: Mapping[str, Any] | None = None) -> None:
        with self._lock:
            if where is None:
                self._entries = []
            else:
                clauses = self._normalise_where(where)
                self._entries = [
                    entry
                    for entry in self._entries
                    if not self._entry_matches(entry, clauses)
                ]
            self._persist()

    def add(
        self,
        *,
        ids: Sequence[str],
        documents: Sequence[str],
        metadatas: Sequence[Mapping[str, Any] | None],
        embeddings: Sequence[Sequence[float]],
    ) -> None:
        if not (len(ids) == len(documents) == len(metadatas) == len(embeddings)):
            raise ValueError(
                "ids, documents, metadatas, and embeddings must be the same length"
            )
        new_entries: list[dict[str, Any]] = []
        for identifier, document, metadata, embedding in zip(
            ids, documents, metadatas, embeddings
        ):
            entry = {
                "id": str(identifier),
                "document": document,
                "metadata": dict(metadata or {}),
                "embedding": list(map(float, embedding)),
            }
            new_entries.append(entry)
        with self._lock:
            existing_ids = {
                entry["id"]: index for index, entry in enumerate(self._entries)
            }
            for entry in new_entries:
                idx = existing_ids.get(entry["id"])
                if idx is not None:
                    self._entries[idx] = entry
                else:
                    self._entries.append(entry)
            self._persist()

    def count(self) -> int:
        return len(self._entries)

    def get(
        self,
        *,
        ids: Sequence[str] | None = None,
        where: Mapping[str, Any] | None = None,
        limit: int | None = None,
        include: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        include = include or []
        with self._lock:
            entries = list(self._entries)
        if where is not None:
            entries = self._filtered_entries(where)
        if ids is not None:
            ids_set = {str(identifier) for identifier in ids}
            entries = [entry for entry in entries if entry["id"] in ids_set]
        if limit is not None and limit >= 0:
            entries = entries[: limit or 0]
        response: dict[str, Any] = {"ids": [[entry["id"] for entry in entries]]}
        if "documents" in include:
            response["documents"] = [[entry.get("document") for entry in entries]]
        if "metadatas" in include:
            response["metadatas"] = [[entry.get("metadata") for entry in entries]]
        if "embeddings" in include:
            response["embeddings"] = [[entry.get("embedding") for entry in entries]]
        return response

    def query(
        self,
        *,
        query_embeddings: Sequence[Sequence[float]],
        n_results: int = 10,
        include: Sequence[str] | None = None,
        where: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        include = include or []
        queries = [self._to_vector(embedding) for embedding in query_embeddings]
        entries = self._filtered_entries(where)
        if not entries:
            return self._empty_query_response(len(queries), include)

        entry_ids = [entry["id"] for entry in entries]
        documents = [entry.get("document") for entry in entries]
        metadatas = [entry.get("metadata") for entry in entries]
        vectors = [self._to_vector(entry.get("embedding", ())) for entry in entries]

        distances_per_query: list[list[float]] = []
        indices_per_query: list[list[int]] = []

        for query in queries:
            scored: list[tuple[float, int]] = []
            for idx, vector in enumerate(vectors):
                similarity = self._cosine(query, vector) if vector else 0.0
                distance = 1.0 - similarity
                scored.append((distance, idx))
            scored.sort(key=lambda item: item[0])
            if n_results >= 0:
                limit = max(1, n_results)
                scored = scored[:limit]
            distances_per_query.append([distance for distance, _ in scored])
            indices_per_query.append([index for _, index in scored])

        response: dict[str, Any] = {"ids": []}
        if "documents" in include:
            response["documents"] = []
        if "metadatas" in include:
            response["metadatas"] = []
        if "distances" in include:
            response["distances"] = []
        if "embeddings" in include:
            response["embeddings"] = []

        for distances, indices in zip(distances_per_query, indices_per_query):
            response["ids"].append([entry_ids[idx] for idx in indices])
            if "documents" in include:
                response["documents"].append([documents[idx] for idx in indices])
            if "metadatas" in include:
                response["metadatas"].append([metadatas[idx] for idx in indices])
            if "distances" in include:
                response["distances"].append(distances)
            if "embeddings" in include:
                response["embeddings"].append(
                    [entries[idx].get("embedding") for idx in indices]
                )
        return response

    @staticmethod
    def _empty_query_response(
        query_count: int, include: Sequence[str]
    ) -> dict[str, Any]:
        response: dict[str, Any] = {"ids": [[] for _ in range(query_count)]}
        if "documents" in include:
            response["documents"] = [[] for _ in range(query_count)]
        if "metadatas" in include:
            response["metadatas"] = [[] for _ in range(query_count)]
        if "distances" in include:
            response["distances"] = [[] for _ in range(query_count)]
        if "embeddings" in include:
            response["embeddings"] = [[] for _ in range(query_count)]
        return response


__all__ = ["Collection"]
