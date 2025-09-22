from __future__ import annotations

import threading
import time

import pytest

from backend.app import create_app
from server import refresh_worker


@pytest.fixture(autouse=True)
def _patch_refresh_worker(monkeypatch: pytest.MonkeyPatch):
    def fake_run(
        query: str,
        budget: int,
        use_llm: bool,
        model: str | None,
        *,
        config,
        extra_seeds=None,
        progress_callback=None,
        db=None,
        frontier_depth=None,
        seed_candidates=None,
    ):
        if progress_callback:
            progress_callback("frontier_start", {"query": query, "budget": budget, "depth": frontier_depth or 4})
            progress_callback("frontier_complete", {"seed_count": 3, "new_domains": 2})
            progress_callback("crawl_start", {"seed_count": 3})
        time.sleep(0.01)
        if progress_callback:
            progress_callback("crawl_complete", {"pages_fetched": 2})
            progress_callback("normalize_complete", {"docs": 1})
            progress_callback(
                "index_complete",
                {"docs_indexed": 1, "skipped": 0, "deduped": 0},
            )
        return {
            "query": query,
            "pages_fetched": 2,
            "docs_indexed": 1,
            "skipped": 0,
            "deduped": 0,
            "duration": 0.05,
            "normalized_docs": [{}],
            "raw_path": None,
            "discovery": {
                "seed_count": 3,
                "new_domains": 2,
                "mode": "manual" if seed_candidates else "discovery",
                "depth": frontier_depth or 4,
                "budget": budget,
                "seeds": [],
            },
            "embedded": 0,
        }

    monkeypatch.setattr(refresh_worker, "run_focused_crawl", fake_run)
    yield


def test_refresh_flow_and_status_polling():
    app = create_app()
    client = app.test_client()

    response = client.post("/api/refresh", json={"query": "manual refresh"})
    assert response.status_code == 202
    payload = response.get_json()
    assert payload["created"] is True
    job_id = payload["job_id"]
    assert isinstance(job_id, str)

    deadline = time.time() + 2
    final = None
    while time.time() < deadline:
        resp = client.get("/api/refresh/status", query_string={"job_id": job_id})
        assert resp.status_code == 200
        data = resp.get_json()
        final = data.get("job")
        if final and final.get("state") == "done":
            break
        time.sleep(0.05)
    assert final is not None
    assert final["state"] == "done"
    assert final["stats"]["docs_indexed"] == 1
    assert final["stats"]["pages_fetched"] == 2
    assert final["stats"]["fetched"] == 2
    assert final["stats"]["updated"] == 1
    assert final["stats"]["embedded"] == 0
    assert final["stats"]["new_domains"] == 2


def test_refresh_deduplicates_active_jobs(monkeypatch: pytest.MonkeyPatch):
    gate = threading.Event()
    release = threading.Event()

    def slow_run(
        query: str,
        budget: int,
        use_llm: bool,
        model: str | None,
        *,
        config,
        extra_seeds=None,
        progress_callback=None,
        db=None,
        frontier_depth=None,
        seed_candidates=None,
    ):
        if progress_callback:
            progress_callback("frontier_start", {"query": query, "budget": budget, "depth": frontier_depth or 4})
            progress_callback("frontier_complete", {"seed_count": 0, "new_domains": 0})
        gate.set()
        release.wait(timeout=2)
        if progress_callback:
            progress_callback("index_complete", {"docs_indexed": 0, "skipped": 0, "deduped": 0})
        return {
            "query": query,
            "pages_fetched": 0,
            "docs_indexed": 0,
            "skipped": 0,
            "deduped": 0,
            "duration": 0.01,
            "normalized_docs": [],
            "raw_path": None,
            "discovery": {
                "seed_count": 0,
                "new_domains": 0,
                "mode": "manual" if seed_candidates else "discovery",
                "depth": frontier_depth or 4,
                "budget": budget,
                "seeds": [],
            },
            "embedded": 0,
        }

    monkeypatch.setattr(refresh_worker, "run_focused_crawl", slow_run)

    app = create_app()
    client = app.test_client()

    first = client.post("/api/refresh", json={"query": "dedupe me"})
    assert first.status_code == 202
    first_payload = first.get_json()
    job_id = first_payload["job_id"]
    gate.wait(timeout=1)

    second = client.post("/api/refresh", json={"query": "dedupe me"})
    assert second.status_code == 200
    second_payload = second.get_json()
    assert second_payload["job_id"] == job_id
    assert second_payload["created"] is False
    assert second_payload["deduplicated"] is True

    release.set()
    deadline = time.time() + 2
    while time.time() < deadline:
        resp = client.get("/api/refresh/status", query_string={"job_id": job_id})
        assert resp.status_code == 200
        job = resp.get_json()["job"]
        if job and job.get("state") == "done":
            break
        time.sleep(0.05)
    else:
        pytest.fail("refresh job did not complete in time")
