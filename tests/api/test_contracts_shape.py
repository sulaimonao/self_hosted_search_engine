from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.app.api.browser import bp as browser_bp
from backend.app.api.chat import bp as chat_bp
from backend.app.api.jobs import bp as jobs_bp
from backend.app.api.overview import bp as overview_bp

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


@pytest.fixture()
def contract_app(tmp_path, monkeypatch):
    app, state_db, config = build_test_app(
        tmp_path,
        monkeypatch,
        blueprints=[chat_bp, jobs_bp, overview_bp, browser_bp],
    )
    app.config["BUNDLE_STORAGE_DIR"] = tmp_path / "bundles"
    return SimpleNamespace(app=app, state_db=state_db, config=config)


def test_core_contract_envelopes(contract_app, monkeypatch):
    client = contract_app.app.test_client()
    state_db = contract_app.state_db

    def fake_post(url, json, stream, timeout):  # noqa: ANN001 - requests compat
        return _DummyResponse(
            {
                "reasoning": "ok",
                "answer": "Hello there",
                "message": {"role": "assistant", "content": "Hello there"},
            }
        )

    monkeypatch.setattr("backend.app.api.chat.requests.post", fake_post)

    chat_payload = {
        "messages": [{"role": "user", "content": "Hi"}],
        "model": "gemma",
        "stream": False,
    }
    chat_response = client.post("/api/chat", json=chat_payload)
    assert chat_response.status_code == 200
    chat_json = chat_response.get_json()
    assert chat_json["ok"] is True
    assert chat_json["data"]["thread_id"]
    assert isinstance(chat_json["data"]["messages"], list)
    assert chat_json["data"]["messages"][0]["content"]

    job_id = state_db.create_job("bundle_export", payload={"demo": True})
    state_db.update_job(job_id, status="succeeded")
    jobs_response = client.get("/api/jobs")
    jobs_json = jobs_response.get_json()
    assert jobs_json["ok"] is True
    assert isinstance(jobs_json["data"]["jobs"], list)

    tab_id = "tab-contract"
    state_db.add_history_entry(tab_id=tab_id, url="https://example.com", title="Example")
    thread_id = state_db.create_llm_thread(title="Contract", origin="browser")
    state_db.bind_tab_thread(tab_id, thread_id)
    state_db.append_llm_message(thread_id=thread_id, role="user", content="Seed")
    state_db.create_task(title="todo", thread_id=thread_id)
    state_db.upsert_memory(
        memory_id="mem-contract",
        scope="thread",
        scope_ref=thread_id,
        key="k",
        value="remember",
        metadata=None,
        strength=0.5,
        thread_id=thread_id,
        task_id=None,
        source_message_id=None,
        embedding_ref=None,
    )
    state_db.upsert_document(
        job_id=None,
        document_id="doc-contract",
        url="https://example.com",
        canonical_url=None,
        site="example.com",
        title="Doc",
        description=None,
        language="en",
        fetched_at=None,
        normalized_path=None,
        text_len=10,
        tokens=5,
        content_hash=None,
        categories=None,
        labels=None,
        source="test",
        verification=None,
    )
    with state_db._conn:
        state_db._conn.execute(
            "INSERT INTO pending_documents(doc_id, url) VALUES(?, ?)",
            ("pend-contract", "https://example.com"),
        )
        state_db._conn.execute(
            "INSERT INTO pending_chunks(doc_id, chunk_index, text) VALUES(?, ?, ?)",
            ("pend-contract", 0, "chunk"),
        )
        state_db._conn.execute(
            "INSERT INTO pending_vectors_queue(doc_id) VALUES(?)",
            ("pend-contract",),
        )
        state_db._conn.execute(
            "INSERT INTO pages(url, title) VALUES(?, ?)",
            ("https://example.com", "Example"),
        )

    overview_response = client.get("/api/overview")
    overview_json = overview_response.get_json()
    assert overview_json["ok"] is True
    data = overview_json["data"]
    assert data["browser"]["history"]["entries"] >= 1
    assert data["llm"]["threads"]["total"] >= 1
    assert data["knowledge"]["documents"] >= 1
    assert data["storage"]

    delete_response = client.delete("/api/browser/history", json={"domain": "example.com"})
    delete_json = delete_response.get_json()
    assert delete_json["ok"] is True
    assert delete_json["data"]["deleted_count"] >= 1

    error_response = client.delete("/api/browser/history", json={})
    assert error_response.status_code == 400
    error_json = error_response.get_json()
    assert error_json["ok"] is False
    assert error_json["error"]["code"] == "FILTER_REQUIRED"
    assert "message" in error_json["error"]
