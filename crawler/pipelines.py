from __future__ import annotations

import json
import sqlite3
from typing import Any

from config import data_dir, load_config
from crawler.utils import now_utc, sha256_text


class JsonlWriterPipeline:
    """Pipeline that persists unique pages and tracks hashes."""

    def open_spider(self, spider: Any) -> None:
        self.config = load_config()
        base_dir = data_dir(self.config)
        base_dir.mkdir(parents=True, exist_ok=True)
        self.pages_path = base_dir / "pages.jsonl"
        self.meta_path = base_dir / "pages_meta.sqlite"
        self.meta_conn = sqlite3.connect(self.meta_path)
        self.meta_conn.execute(
            "CREATE TABLE IF NOT EXISTS page_hashes (hash TEXT PRIMARY KEY, url TEXT, fetched_at TEXT)"
        )
        self.meta_conn.commit()
        self.file = open(self.pages_path, "a", encoding="utf-8")

    def close_spider(self, spider: Any) -> None:
        if hasattr(self, "file"):
            self.file.close()
        if hasattr(self, "meta_conn"):
            self.meta_conn.close()

    def process_item(self, item: Any, spider: Any) -> Any:
        text = item.get("text", "") or ""
        content_hash = sha256_text(text)
        cur = self.meta_conn.cursor()
        cur.execute("SELECT 1 FROM page_hashes WHERE hash=?", (content_hash,))
        if cur.fetchone():
            return item
        record = {
            "url": item.get("url"),
            "title": item.get("title", ""),
            "text": text,
            "domain": item.get("domain", ""),
            "fetched_at": item.get("fetched_at") or now_utc(),
            "hash": content_hash,
        }
        self.file.write(json.dumps(record, ensure_ascii=False) + "\n")
        cur.execute(
            "INSERT OR REPLACE INTO page_hashes(hash, url, fetched_at) VALUES (?, ?, ?)",
            (content_hash, record["url"], record["fetched_at"]),
        )
        self.meta_conn.commit()
        return item
