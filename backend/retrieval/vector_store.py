"""Minimal pure-Python vector store for semantic retrieval."""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Mapping, Sequence


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
        self._load()

    def _load(self) -> None:
        self._documents: list[dict[str, object]] = []
        if not self._index_path.exists():
            return
        try:
            with self._index_path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, ValueError):
            payload = {}
        documents = payload.get("documents")
        if isinstance(documents, list):
            cleaned: list[dict[str, object]] = []
            for doc in documents:
                if not isinstance(doc, dict):
                    continue
                embedding = doc.get("embedding")
                if not isinstance(embedding, list):
                    continue
                cleaned.append(
                    {
                        "doc_id": str(doc.get("doc_id", "")),
                        "url": str(doc.get("url", "")),
                        "title": str(doc.get("title", "")),
                        "text": str(doc.get("text", "")),
                        "embedding": [float(value) for value in embedding],
                    }
                )
            self._documents = cleaned
        else:
            self._documents = []

    def _persist(self) -> None:
        tmp_index = self._index_path.with_suffix(".json.tmp")
        payload = {"documents": self._documents}
        with tmp_index.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        os.replace(tmp_index, self._index_path)

    def reset(self) -> None:
        self._documents = []
        self._persist()

    def upsert_many(self, documents: Iterable[VectorDocument]) -> tuple[int, int]:
        changed = 0
        skipped = 0
        doc_map: dict[str, int] = {}
        for idx, doc in enumerate(self._documents):
            key = str(doc.get("doc_id") or doc.get("url", ""))
            if key:
                doc_map[key] = idx
        updated_docs: list[dict[str, object]] = []
        for doc in documents:
            key = doc.doc_id or doc.url or f"doc:{len(self._documents) + len(updated_docs)}"
            vector = [float(value) for value in doc.embedding]
            metadata = {
                "doc_id": doc.doc_id,
                "url": doc.url,
                "title": doc.title,
                "text": doc.text,
                "embedding": vector,
            }
            if key in doc_map:
                idx = doc_map[key]
                self._documents[idx] = metadata
                changed += 1
                continue
            updated_docs.append(metadata)
            changed += 1
        if updated_docs:
            self._documents.extend(updated_docs)
        self._persist()
        return changed, skipped

    def query(self, embedding: Sequence[float], k: int = 5) -> List[VectorHit]:
        if not self._documents:
            return []
        vector = [float(value) for value in embedding]
        if not vector:
            return []
        query_norm = math.sqrt(sum(x * x for x in vector))
        if query_norm <= 1e-12:
            return []
        scores: list[tuple[float, dict[str, object]]] = []
        for doc in self._documents:
            target = doc.get("embedding") or []
            if len(target) != len(vector):
                continue
            denom = query_norm * math.sqrt(sum(x * x for x in target))
            if denom <= 1e-12:
                similarity = 0.0
            else:
                similarity = sum(a * b for a, b in zip(vector, target)) / denom
            scores.append((similarity, doc))
        if not scores:
            return []
        scores.sort(key=lambda item: item[0], reverse=True)
        limit = max(1, int(k))
        hits: List[VectorHit] = []
        for similarity, doc in scores[:limit]:
            doc_identifier = doc.get("doc_id") or doc.get("url") or ""
            hits.append(
                VectorHit(
                    url=str(doc.get("url", "")),
                    title=str(doc.get("title", "")),
                    snippet=str(doc.get("text", ""))[:280],
                    score=float(similarity),
                    doc_id=str(doc_identifier),
                )
            )
        return hits

    def to_metadata(self) -> Mapping[str, object]:
        dims = 0
        for doc in self._documents:
            embedding = doc.get("embedding")
            if isinstance(embedding, list) and embedding:
                dims = len(embedding)
                break
        return {
            "documents": len(self._documents),
            "dimensions": dims,
        }


__all__ = ["LocalVectorStore", "VectorDocument", "VectorHit"]
