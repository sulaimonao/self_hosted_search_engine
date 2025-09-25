"""File-system backed storage for fetched pages used by the agent."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, MutableMapping


@dataclass(slots=True)
class StoredDocument:
    url: str
    title: str
    text: str
    sha256: str
    source: str | None = None
    metadata: Mapping[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "url": self.url,
            "title": self.title,
            "text": self.text,
            "sha256": self.sha256,
        }
        if self.source is not None:
            payload["source"] = self.source
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload


class DocumentStore:
    """Persist normalized page captures for incremental indexing."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path_for(self, url: str) -> Path:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return self.root / f"{digest}.json"

    def save(self, document: StoredDocument) -> Path:
        path = self._path_for(document.url)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(document.to_dict(), handle, ensure_ascii=False, indent=2)
        return path

    def load(self, url: str) -> StoredDocument | None:
        path = self._path_for(url)
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as handle:
            payload: MutableMapping[str, object] = json.load(handle)
        text = str(payload.get("text", ""))
        if not text:
            return None
        return StoredDocument(
            url=str(payload.get("url", url)),
            title=str(payload.get("title", "")),
            text=text,
            sha256=str(payload.get("sha256", "")),
            source=payload.get("source"),
            metadata=payload.get("metadata"),
        )

    def iter_documents(self, urls: Iterable[str] | None = None) -> Iterable[StoredDocument]:
        if urls is None:
            for path in sorted(self.root.glob("*.json")):
                with path.open("r", encoding="utf-8") as handle:
                    payload = json.load(handle)
                text = str(payload.get("text", ""))
                if not text:
                    continue
                yield StoredDocument(
                    url=str(payload.get("url", "")),
                    title=str(payload.get("title", "")),
                    text=text,
                    sha256=str(payload.get("sha256", "")),
                    source=payload.get("source"),
                    metadata=payload.get("metadata"),
                )
            return
        for url in urls:
            doc = self.load(url)
            if doc is not None:
                yield doc


__all__ = ["DocumentStore", "StoredDocument"]
