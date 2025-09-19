import json
import time

from backend.app import create_app
from backend.app.config import AppConfig
from backend.app.indexer.incremental import incremental_index
from backend.app.pipeline.normalize import normalize
from search.seeds import DEFAULT_SEEDS_PATH, merge_curated_seeds


def test_end_to_end_index_and_search(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("FOCUSED_CRAWL_ENABLED", "0")
    config = AppConfig.from_env()
    config.ensure_dirs()

    curated_path = data_dir / "seeds" / "curated_seeds.jsonl"
    curated_path.parent.mkdir(parents=True, exist_ok=True)
    curated_path.write_text(
        json.dumps(
            {
                "url": "https://example.com/docs",
                "value_prior": 1.2,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    store_path = data_dir / "seeds.jsonl"
    merge_curated_seeds(curated_path, store_path=store_path)

    raw_dir = config.crawl_raw_dir
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_record = {
        "query": "example",
        "url": "https://example.com/docs",
        "status": 200,
        "title": "Example Docs",
        "html": "<html><head><title>Example</title></head><body><h1>Example Guide</h1><p>Content.</p></body></html>",
        "fetched_at": time.time(),
    }
    raw_path = raw_dir / "sample.jsonl"
    with raw_path.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(raw_record))

    docs = normalize(raw_dir, config.normalized_path, append=False, sources=[raw_path])
    incremental_index(
        config.index_dir,
        config.ledger_path,
        config.simhash_path,
        config.last_index_time_path,
        docs,
    )

    app = create_app()
    app.testing = True
    client = app.test_client()
    response = client.get("/api/search", query_string={"q": "Example Guide"})
    payload = response.get_json()
    assert payload["results"], "expected indexed search results"
