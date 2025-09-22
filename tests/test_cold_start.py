import time

import pytest

from backend.app import create_app
from backend.app.config import AppConfig
from backend.app.indexer.incremental import incremental_index


def fake_run_focused_crawl(
    query,
    budget,
    use_llm,
    model,
    *,
    config: AppConfig,
    extra_seeds=None,
    frontier_budget=None,
    frontier_depth=None,
    discovery_metadata_path=None,
    progress_callback=None,
):
    config.ensure_dirs()
    doc = {
        "url": f"https://local-doc/{query.replace(' ', '-')}",
        "title": "Local Seed",
        "h1h2": "Local Heading",
        "body": "This locally generated document covers python packaging basics for testing the incremental index pipeline.",
        "lang": "en",
    }
    print(f"[fake] indexing document for query '{query}'")
    incremental_index(
        config.index_dir,
        config.ledger_path,
        config.simhash_path,
        config.last_index_time_path,
        [doc],
    )
    discovery = {
        "query": query,
        "seed_count": 1,
        "new_domains_count": 1,
    }
    return {
        "query": query,
        "pages_fetched": 1,
        "docs_indexed": 1,
        "skipped": 0,
        "deduped": 0,
        "embedded": 1,
        "new_domains": 1,
        "duration": 0.01,
        "normalized_docs": [doc],
        "raw_path": None,
        "discovery": discovery,
    }


def test_cold_start_triggers_background_job(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("FOCUSED_CRAWL_ENABLED", "1")
    monkeypatch.setenv("SMART_MIN_RESULTS", "1")
    monkeypatch.setenv("SMART_TRIGGER_COOLDOWN", "0")
    monkeypatch.setenv("FOCUSED_CRAWL_BUDGET", "5")

    monkeypatch.setattr(
        "backend.app.jobs.focused_crawl.run_focused_crawl",
        fake_run_focused_crawl,
    )

    app = create_app()
    app.testing = True
    client = app.test_client()

    response = client.get("/api/search", query_string={"q": "python packaging"})
    payload = response.get_json()
    assert payload["status"] == "focused_crawl_running"
    job_id = payload["job_id"]
    assert job_id

    for _ in range(20):
        job_response = client.get(f"/api/jobs/{job_id}/status")
        job_payload = job_response.get_json()
        if job_payload["state"] == "done":
            result = job_payload.get("result", {})
            assert result.get("docs_indexed") == 1
            break
        time.sleep(0.1)
    else:
        pytest.fail("Focused crawl job did not finish")

    config = AppConfig.from_env()
    assert config.last_index_time_path.exists()
    assert int(config.last_index_time_path.read_text().strip()) > 0

    follow_up = client.get("/api/search", query_string={"q": "python packaging"})
    follow_payload = follow_up.get_json()
    assert follow_payload["status"] == "ok"
    assert follow_payload["results"], "expected indexed results after cold start"
    urls = [item["url"] for item in follow_payload["results"]]
    assert any(url.startswith("https://local-doc/") for url in urls)
