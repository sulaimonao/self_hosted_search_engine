"""Pipelines to persist crawl output to disk."""

from __future__ import annotations

import json
import hashlib
import time
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
        canonical = item.get("canonical_url")
        if isinstance(canonical, str) and canonical:
            canonical_url = canonical
        else:
            canonical_url = url
        lang = item.get("lang") if isinstance(item.get("lang"), str) else ""
        text = item.get("text", "")
        if isinstance(text, str):
            body_text = text
        else:
            body_text = ""
        content_hash = hashlib.sha256(body_text.encode("utf-8", errors="ignore")).hexdigest()
        fetched_at = item.get("fetched_at")
        try:
            fetched_at_ts = float(fetched_at) if fetched_at is not None else time.time()
        except (TypeError, ValueError):
            fetched_at_ts = time.time()
        outlinks = item.get("outlinks") or []
        if isinstance(outlinks, str):
            outlinks_list = [part.strip() for part in outlinks.split(",") if part.strip()]
        elif isinstance(outlinks, list):
            outlinks_list = [str(link) for link in outlinks[:200]]
        else:
            outlinks_list = []
        normalized = {
            "url": url,
            "canonical_url": canonical_url,
            "title": item.get("title", ""),
            "text": body_text,
            "lang": lang or "",
            "content_hash": content_hash,
            "fetched_at": fetched_at_ts,
            "outlinks": outlinks_list,
        }
        self._normalized_handle.write(json.dumps(normalized, ensure_ascii=False) + "\n")
        self._normalized_handle.flush()
        return item
