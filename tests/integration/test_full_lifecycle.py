from __future__ import annotations

import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.app.api.browser import bp as browser_bp
from backend.app.api.chat import bp as chat_bp
from backend.app.api.bundle import bp as bundle_bp
from backend.app.api.hydraflow import bp as hydraflow_bp
from backend.app.api.jobs import bp as jobs_bp
from backend.app.api.refresh import bp as refresh_bp

from tests.backend_app_helpers import build_test_app


class _DummyResponse:
    def __init__(self, payload: dict):
        self._payload = payload
        self.status_code = 200
        self.headers: dict[str, str] = {}

    def json(self):  # noqa: D401 - mimic requests.Response
        return self._payload

    def close(self):  # pragma: no cover - compatibility shim
        return None


class _DummyRefreshWorker:
    def __init__(self, state_db):
        self.state_db = state_db
        self.jobs: dict[str, dict[str, str]] = {}

    def enqueue(self, query, **_: object):  # noqa: ANN001 - signature compat
        job_id = uuid.uuid4().hex
        snapshot = {"id": job_id, "state": "queued", "query": query}
        self.jobs[job_id] = snapshot
        if self.state_db:
            self.state_db.create_job(
                "focused_crawl",
                job_id=job_id,
                payload={"query": query},
                status="queued",
            )
        return job_id, {"job": snapshot}, True

    def status(self, job_id=None, query=None):  # noqa: ANN001 - compatibility
        if job_id and job_id in self.jobs:
            return {"job": self.jobs[job_id]}
        if query:
            for job in self.jobs.values():
                if job.get("query") == query:
                    return {"job": job}
        return {"job": None}


@pytest.fixture()
def lifecycle_app(tmp_path, monkeypatch):
    app, state_db, config = build_test_app(
        tmp_path,
        monkeypatch,
        blueprints=[
            browser_bp,
            chat_bp,
            hydraflow_bp,
            bundle_bp,
            jobs_bp,
            refresh_bp,
        ],
    )
    bundle_dir = tmp_path / "bundles"
    bundle_dir.mkdir(exist_ok=True)
    app.config["BUNDLE_STORAGE_DIR"] = bundle_dir
    worker = _DummyRefreshWorker(state_db)
    app.config["REFRESH_WORKER"] = worker
    return SimpleNamespace(app=app, state_db=state_db, worker=worker, bundle_dir=bundle_dir)


def test_full_backend_lifecycle(lifecycle_app, monkeypatch, tmp_path):
    client = lifecycle_app.app.test_client()
    state_db = lifecycle_app.state_db

    def fake_post(url, json, stream, timeout):  # noqa: ANN001 - requests compat
        return _DummyResponse(
            {
                "reasoning": "test",
                "answer": "Lifecycle ok",
                "message": {"role": "assistant", "content": "Lifecycle ok"},
            }
        )

    monkeypatch.setattr("backend.app.api.chat.requests.post", fake_post)

    tab_id = "tab-lifecycle"
    thread_resp = client.post(f"/api/browser/tabs/{tab_id}/thread", json={"title": "Lifecycle"})
    assert thread_resp.status_code == 200
    thread_id = thread_resp.get_json()["thread_id"]

    chat_resp = client.post(
        "/api/chat",
        json={"messages": [{"role": "user", "content": "Hi"}], "tab_id": tab_id, "stream": False},
    )
    chat_json = chat_resp.get_json()
    assert chat_json["ok"] is True
    thread_id = chat_json["data"]["thread_id"]
    state_db.append_llm_message(thread_id=thread_id, role="assistant", content="Lifecycle ok")

    task_resp = client.post(
        "/api/tasks",
        json={"title": "Follow up", "thread_id": thread_id},
    )
    assert task_resp.status_code == 201
    task_id = task_resp.get_json()["id"]
    assert task_id

    state_db.add_history_entry(tab_id=tab_id, url="https://example.com", title="Example")

    refresh_resp = client.post("/api/refresh", json={"query": "site:example.com"})
    assert refresh_resp.status_code == 202
    refresh_payload = refresh_resp.get_json()
    refresh_job_id = refresh_payload["job_id"]
    job_record = state_db.get_job(refresh_job_id)
    assert job_record["type"] == "focused_crawl"

    export_resp = client.get(
        "/api/export/bundle",
        query_string=[
            ("component", "threads"),
            ("component", "messages"),
            ("component", "tasks"),
            ("component", "browser_history"),
        ],
    )
    export_json = export_resp.get_json()
    bundle_path = Path(export_json["bundle_path"])
    assert bundle_path.exists()
    export_job = state_db.get_job(export_json["job_id"])
    assert export_job["type"] == "bundle_export"

    import_tmp = tmp_path / "import"
    import_app, import_state, _ = build_test_app(
        import_tmp,
        monkeypatch,
        blueprints=[bundle_bp, jobs_bp, hydraflow_bp, browser_bp],
    )
    import_app.config["BUNDLE_STORAGE_DIR"] = lifecycle_app.bundle_dir
    import_client = import_app.test_client()
    import_resp = import_client.post("/api/import/bundle", json={"bundle_path": str(bundle_path)})
    assert import_resp.status_code == 200
    import_json = import_resp.get_json()
    assert import_json["imported"]["threads"] >= 1

    imported_threads = import_state.list_llm_threads(limit=10)
    assert any(record["id"] == thread_id for record in imported_threads)
    imported_messages = import_state.list_llm_messages(thread_id, limit=10)
    assert imported_messages
    imported_tasks = import_state.list_tasks(thread_id=thread_id, limit=10)
    assert imported_tasks
    imported_history = import_state.query_history(limit=10)
    assert imported_history
