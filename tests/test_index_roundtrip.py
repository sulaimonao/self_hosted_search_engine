import json
import os
from pathlib import Path

import yaml
from whoosh import index
from whoosh.qparser import QueryParser

import index_build
from config import index_dir, load_config, reset_config_cache
from crawler.utils import sha256_text


def write_config(tmp_path: Path) -> Path:
    config = {
        "crawler": {
            "user_agent": "TestBot/0.1",
            "obey_robots": True,
            "download_delay_sec": 0.1,
            "concurrent_requests": 2,
            "concurrent_per_domain": 2,
            "depth_limit": 1,
            "per_domain_page_cap": 10,
            "use_js_fallback": False,
            "js_fallback_threshold_chars": 200,
            "frontier_db": str(tmp_path / "frontier.sqlite"),
            "robots_cache_dir": str(tmp_path / "robots"),
            "max_pages_total": 100,
        },
        "seeds": {
            "urls_file": str(tmp_path / "seeds.txt"),
            "domains_file": str(tmp_path / "domains.txt"),
            "sitemaps_file": str(tmp_path / "sitemaps.txt"),
        },
        "index": {
            "dir": str(tmp_path / "index"),
            "analyzer": "stemming",
            "field_boosts": {"title": 2.0, "content": 1.0},
            "incremental": True,
        },
        "ui": {"host": "127.0.0.1", "port": 5001, "page_len": 5},
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return config_path


def test_index_roundtrip(tmp_path, monkeypatch):
    config_path = write_config(tmp_path)
    monkeypatch.setenv("SELFSEARCH_CONFIG", str(config_path))
    reset_config_cache()
    cfg = load_config(reload=True)

    data_path = (tmp_path / "pages.jsonl")
    data_path.write_text("", encoding="utf-8")
    docs = [
        {
            "url": "https://example.com/",
            "title": "Example Domain",
            "text": "This domain is for testing examples only.",
            "domain": "example.com",
        },
        {
            "url": "https://example.com/docs",
            "title": "Example Docs",
            "text": "Documentation and guides for examples.",
            "domain": "example.com",
        },
    ]
    with data_path.open("w", encoding="utf-8") as fh:
        for doc in docs:
            doc_with_hash = dict(doc)
            doc_with_hash["hash"] = sha256_text(doc["text"])
            fh.write(json.dumps(doc_with_hash) + "\n")

    base_data_dir = Path(cfg["crawler"]["frontier_db"]).parent
    base_data_dir.mkdir(parents=True, exist_ok=True)
    # Move pages file into expected data directory
    target_path = base_data_dir / "pages.jsonl"
    target_path.write_text(data_path.read_text(encoding="utf-8"), encoding="utf-8")

    index_build.main(["full"])

    ix = index.open_dir(index_dir(cfg))
    with ix.searcher() as searcher:
        parser = QueryParser("content", schema=ix.schema)
        query = parser.parse("documentation")
        results = searcher.search(query, limit=5)
        assert len(results) == 1
        assert results[0]["title"] == "Example Docs"
