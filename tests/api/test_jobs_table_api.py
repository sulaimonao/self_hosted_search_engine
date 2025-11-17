import types

import pytest
from flask import Flask

from backend.app.api import jobs as jobs_api
from backend.app.db.store import AppStateDB
from server import refresh_worker


def test_jobs_table_endpoints(tmp_path):
    db_path = tmp_path / "jobs-state.sqlite3"
    state_db = AppStateDB(db_path)
    job_id = state_db.create_job("bundle_export")
    state_db.update_job(job_id, status="running")
    thread_id = state_db.create_llm_thread(title="Job thread")
    task_id = state_db.create_task(title="Job task", thread_id=thread_id)
    job_meta = state_db.create_job(
        "bundle_import",
        task_id=task_id,
        thread_id=thread_id,
        status="queued",
    )
    state_db.update_job(job_meta, status="queued")
    app = Flask(__name__)
    app.config["APP_STATE_DB"] = state_db
    app.register_blueprint(jobs_api.bp)
    client = app.test_client()
    list_resp = client.get("/api/jobs?status=running")
    assert list_resp.status_code == 200
    items = list_resp.get_json()["items"]
    assert any(item["id"] == job_id for item in items)
    detail = client.get(f"/api/jobs/{job_id}")
    assert detail.status_code == 200
    payload = detail.get_json()["job"]
    assert payload["status"] == "running"
    missing = client.get("/api/jobs/does-not-exist")
    assert missing.status_code == 404
    type_filtered = client.get("/api/jobs", query_string={"type": "bundle_import"})
    assert type_filtered.status_code == 200
    filtered_items = type_filtered.get_json()["items"]
    assert len(filtered_items) == 1
    assert filtered_items[0]["id"] == job_meta
    assert filtered_items[0]["task_id"] == task_id
    assert filtered_items[0]["thread_id"] == thread_id


def test_refresh_worker_records_jobs(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(refresh_worker.RefreshWorker, "_worker_loop", lambda self: None)

    def fake_crawl(
        query: str,
        budget: int,
        use_llm: bool,
        model: str | None,
        *,
        config,
        manual_seeds=None,
        frontier_depth=None,
        progress_callback=None,
        db=None,
        state_db=None,
        job_id=None,
    ):
        if progress_callback:
            progress_callback("frontier_start", {"seed_count": 1})
            progress_callback("index_complete", {"docs_indexed": 1, "skipped": 0, "deduped": 0})
        return {
            "pages_fetched": 1,
            "docs_indexed": 1,
            "skipped": 0,
            "deduped": 0,
            "embedded": 0,
            "new_domains": 0,
            "normalized_docs": [{}],
        }

    monkeypatch.setattr(refresh_worker, "run_focused_crawl", fake_crawl)

    state_db = AppStateDB(tmp_path / "refresh-jobs.sqlite3")
    config = types.SimpleNamespace(
        normalized_path=tmp_path / "normalized.jsonl",
        focused_budget=2,
    )
    worker = refresh_worker.RefreshWorker(config, state_db=state_db)
    job_id, _snapshot, created = worker.enqueue("demo refresh")
    assert created is True
    worker._run_job(job_id)
    job_record = state_db.get_job(job_id)
    assert job_record["type"] == "focused_crawl"
    assert job_record["status"] == "succeeded"
    assert job_record["result"]["stats"]["docs_indexed"] == 1
