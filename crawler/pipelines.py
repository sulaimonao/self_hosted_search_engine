"""Pipelines to persist crawl output to disk."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


class NormalizePipeline:
    """Write raw and normalized crawl output to JSONL files."""

    def __init__(self) -> None:
        self.raw_path: Path | None = None
        self.normalized_path: Path | None = None
        self._raw_handle = None
        self._normalized_handle = None
        self._seen_urls: set[str] = set()

    def open_spider(self, spider) -> None:  # type: ignore[override]
        store = Path(getattr(spider, "crawl_store", "./data/crawl"))
        store.mkdir(parents=True, exist_ok=True)
        self.raw_path = store / "raw.jsonl"
        self.normalized_path = store / "normalized.jsonl"
        self._raw_handle = self.raw_path.open("a", encoding="utf-8")
        self._normalized_handle = self.normalized_path.open("a", encoding="utf-8")

    def close_spider(self, spider) -> None:  # type: ignore[override]
        if self._raw_handle:
            self._raw_handle.close()
        if self._normalized_handle:
            self._normalized_handle.close()

    def process_item(self, item: Dict[str, Any], spider):  # type: ignore[override]
        assert self._raw_handle is not None
        assert self._normalized_handle is not None

        raw_payload = json.dumps(item, ensure_ascii=False)
        self._raw_handle.write(raw_payload + "\n")
        self._raw_handle.flush()

        url = item.get("url")
        if isinstance(url, str):
            if url in self._seen_urls:
                return item
            self._seen_urls.add(url)
        normalized = {
            "url": url,
            "title": item.get("title", ""),
            "text": item.get("text", ""),
        }
        self._normalized_handle.write(json.dumps(normalized, ensure_ascii=False) + "\n")
        self._normalized_handle.flush()
        return item
