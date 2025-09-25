"""Minimal numpy-backed vector store for semantic retrieval."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Mapping, Sequence

import numpy as np


@dataclass(slots=True)
class VectorHit:
    url: str
    title: str
    snippet: str
    score: float
    doc_id: str


@dataclass(slots=True)
class VectorDocument:
    doc_id: str
    url: str
    title: str
    text: str
    embedding: Sequence[float]


class LocalVectorStore:
    """Persist embeddings alongside document metadata."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._index_path = self.root / "index.json"
        self._embedding_path = self.root / "embeddings.npy"
        self._load()

    def _load(self) -> None:
        self._documents: list[dict[str, object]] = []
        self._matrix: np.ndarray | None = None
        if self._index_path.exists():
            with self._index_path.open("r", encoding="utf-8") as handle:
                self._documents = json.load(handle)
        if self._embedding_path.exists():
            self._matrix = np.load(self._embedding_path)
        if self._matrix is not None and len(self._documents) != len(self._matrix):
            # Repair mismatch by truncating to the smaller length
            size = min(len(self._documents), len(self._matrix))
            self._documents = self._documents[:size]
            self._matrix = self._matrix[:size]

    def _persist(self) -> None:
        tmp_index = self._index_path.with_suffix(".json.tmp")
        tmp_embeddings = self._embedding_path.with_suffix(".npy.tmp")
        with tmp_index.open("w", encoding="utf-8") as handle:
            json.dump(self._documents, handle, ensure_ascii=False, indent=2)
        if self._matrix is None:
            matrix = np.zeros((0, 0), dtype=np.float32)
        else:
            matrix = self._matrix.astype(np.float32)
        with tmp_embeddings.open("wb") as handle:
            np.save(handle, matrix)
        os.replace(tmp_index, self._index_path)
        os.replace(tmp_embeddings, self._embedding_path)

    def reset(self) -> None:
        self._documents = []
        self._matrix = np.zeros((0, 0), dtype=np.float32)
        self._persist()

    def upsert_many(self, documents: Iterable[VectorDocument]) -> tuple[int, int]:
        changed = 0
        skipped = 0
        doc_map: dict[str, int] = {}
        for idx, doc in enumerate(self._documents):
            url = str(doc.get("url", ""))
            if url:
                doc_map[url] = idx
        vectors: list[np.ndarray] = []
        updated_docs: list[dict[str, object]] = []
        for doc in documents:
            key = doc.url
            vector = np.asarray(list(doc.embedding), dtype=np.float32)
            metadata = {
                "doc_id": doc.doc_id,
                "url": doc.url,
                "title": doc.title,
                "text": doc.text,
            }
            if key in doc_map:
                idx = doc_map[key]
                self._documents[idx] = metadata
                if self._matrix is not None:
                    self._matrix[idx] = vector
                changed += 1
                continue
            updated_docs.append(metadata)
            vectors.append(vector)
            changed += 1
        if updated_docs:
            self._documents.extend(updated_docs)
            if vectors:
                stacked_new = np.vstack(vectors)
                if self._matrix is None or not len(self._matrix):
                    self._matrix = stacked_new
                else:
                    self._matrix = np.vstack([self._matrix, stacked_new])
            elif self._matrix is None:
                self._matrix = np.zeros((0, 0), dtype=np.float32)
        self._persist()
        return changed, skipped

    def query(self, embedding: Sequence[float], k: int = 5) -> List[VectorHit]:
        if self._matrix is None or not len(self._documents):
            return []
        query = np.asarray(list(embedding), dtype=np.float32)
        if query.ndim != 1:
            raise ValueError("embedding must be a 1D vector")
        matrix = self._matrix
        if matrix.ndim != 2:
            return []
        norms = np.linalg.norm(matrix, axis=1)
        denom = (np.linalg.norm(query) * norms)
        denom = np.where(denom == 0, 1e-9, denom)
        scores = (matrix @ query) / denom
        order = np.argsort(scores)[::-1]
        limit = max(1, int(k))
        hits: List[VectorHit] = []
        for idx in order[:limit]:
            doc = self._documents[int(idx)]
            score = float(scores[int(idx)])
            hits.append(
                VectorHit(
                    url=str(doc.get("url", "")),
                    title=str(doc.get("title", "")),
                    snippet=str(doc.get("text", ""))[:280],
                    score=score,
                    doc_id=str(doc.get("doc_id", idx)),
                )
            )
        return hits

    def to_metadata(self) -> Mapping[str, object]:
        return {
            "documents": len(self._documents),
            "dimensions": int(self._matrix.shape[1]) if self._matrix is not None and self._matrix.size else 0,
        }


__all__ = ["LocalVectorStore", "VectorDocument", "VectorHit"]
