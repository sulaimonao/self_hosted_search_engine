import json
import time
from pathlib import Path

import pytest

from backend.app import create_app
from backend.app.config import AppConfig
from backend.app.indexer.incremental import incremental_index


def fake_ollama_request(url, model, system, prompt):
    if "Create a JSON object" in prompt:
        return json.dumps(
            {
                "tasks": ["Collect docs", "Summarize", "List references"],
                "sources": [
                    "https://example.com/one",
                    "https://example.com/two",
                    "https://example.com/three",
                ],
            }
        )
    return "# Research Report\n\n- Key point one[^1]\n- Key point two[^2]\n- Key point three[^3]\n\n[^1]: https://example.com/one\n[^2]: https://example.com/two\n[^3]: https://example.com/three"


def fake_run_focused_crawl(query, budget, use_llm, model, *, config: AppConfig, extra_seeds=None):
    config.ensure_dirs()
    doc = {
        "url": "https://example.com/one",
        "title": "Example Doc",
        "h1h2": "Example H1",
        "body": "Example body content for research aggregation.",
        "lang": "en",
    }
    incremental_index(
        config.index_dir,
        config.ledger_path,
        config.simhash_path,
        config.last_index_time_path,
        [doc],
    )
    return {
        "query": query,
        "pages_fetched": 1,
        "docs_indexed": 1,
        "skipped": 0,
        "deduped": 0,
        "duration": 0.01,
        "normalized_docs": [doc],
        "raw_path": None,
    }


def test_research_job_creates_report(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("FOCUSED_CRAWL_ENABLED", "1")

    monkeypatch.setattr(
        "backend.app.jobs.research._ollama_request",
        lambda *args, **kwargs: fake_ollama_request(*args, **kwargs),
    )
    monkeypatch.setattr("backend.app.jobs.focused_crawl.run_focused_crawl", fake_run_focused_crawl)
    monkeypatch.setattr("backend.app.jobs.research.run_focused_crawl", fake_run_focused_crawl)

    app = create_app()
    app.testing = True
    client = app.test_client()

    response = client.post("/api/research", json={"query": "python packaging", "budget": 5})
    payload = response.get_json()
    assert "job_id" in payload
    job_id = payload["job_id"]

    for _ in range(30):
        job_response = client.get(f"/api/jobs/{job_id}/status")
        job_payload = job_response.get_json()
        if job_payload["state"] == "done":
            result = job_payload.get("result", {})
            report_path = result.get("report_path")
            assert report_path
            break
        time.sleep(0.1)
    else:
        pytest.fail("Research job did not complete")

    report_file = Path(report_path)
    assert report_file.exists()
    content = report_file.read_text(encoding="utf-8")
    assert content.count("[^") >= 3
