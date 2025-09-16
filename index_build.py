#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Iterable

from whoosh import index
from whoosh.analysis import SimpleAnalyzer, StemmingAnalyzer
from whoosh.fields import ID, KEYWORD, Schema, TEXT

from config import data_dir, index_dir, load_config


class IndexMetadata:
    def __init__(self, path: Path):
        import sqlite3

        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS documents (url TEXT PRIMARY KEY, hash TEXT)"
        )
        self.conn.commit()

    def get_hash(self, url: str) -> str | None:
        cur = self.conn.execute("SELECT hash FROM documents WHERE url=?", (url,))
        row = cur.fetchone()
        return row[0] if row else None

    def set_hash(self, url: str, content_hash: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO documents(url, hash) VALUES(?, ?)",
            (url, content_hash),
        )

    def remove(self, url: str) -> None:
        self.conn.execute("DELETE FROM documents WHERE url=?", (url,))

    def flush(self) -> None:
        self.conn.commit()

    def close(self) -> None:
        self.conn.commit()
        self.conn.close()

    def __enter__(self) -> "IndexMetadata":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


def load_documents(pages_path: Path) -> Iterable[dict]:
    with pages_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def build_schema(cfg) -> Schema:
    analyzer_name = cfg["index"].get("analyzer", "stemming")
    if analyzer_name == "simple":
        analyzer = SimpleAnalyzer()
    else:
        analyzer = StemmingAnalyzer()
    boosts = cfg["index"].get("field_boosts", {})
    return Schema(
        url=ID(stored=True, unique=True),
        title=TEXT(stored=True, analyzer=analyzer, field_boost=float(boosts.get("title", 1.0))),
        content=TEXT(stored=True, analyzer=analyzer, field_boost=float(boosts.get("content", 1.0))),
        domain=KEYWORD(stored=True, lowercase=True, commas=False, scorable=False),
        hash=ID(stored=True),
    )


def rebuild(mode: str, cfg) -> None:
    base_data_dir = data_dir(cfg)
    pages_path = base_data_dir / "pages.jsonl"
    if not pages_path.exists():
        raise SystemExit(f"No crawled data found at {pages_path}. Run a crawl first.")

    index_path = index_dir(cfg)
    meta_path = base_data_dir / "index_meta.sqlite"

    if mode == "full" and index_path.exists():
        shutil.rmtree(index_path)
    if mode == "full" and meta_path.exists():
        meta_path.unlink()

    index_path.mkdir(parents=True, exist_ok=True)
    schema = build_schema(cfg)
    if index.exists_in(index_path):
        ix = index.open_dir(index_path)
    else:
        ix = index.create_in(index_path, schema)

    indexed = 0
    skipped = 0
    with ix.writer(limitmb=256, procs=0) as writer, IndexMetadata(meta_path) as meta:
        for doc in load_documents(pages_path):
            url = doc.get("url")
            content_hash = doc.get("hash")
            if not url or not content_hash:
                continue
            existing = meta.get_hash(url)
            if existing == content_hash and cfg["index"].get("incremental", True):
                skipped += 1
                continue
            writer.update_document(
                url=url,
                title=doc.get("title", ""),
                content=doc.get("text", ""),
                domain=doc.get("domain", ""),
                hash=content_hash,
            )
            meta.set_hash(url, content_hash)
            indexed += 1
        meta.flush()
    print(f"Indexed {indexed} documents ({skipped} skipped). Index stored at {index_path}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Build or update the Whoosh index")
    parser.add_argument("mode", choices=["full", "update"], nargs="?", default="update")
    args = parser.parse_args(argv)
    cfg = load_config()
    rebuild(args.mode, cfg)


if __name__ == "__main__":
    main()
