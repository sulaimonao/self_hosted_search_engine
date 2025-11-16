import uuid
from pathlib import Path

from flask import Flask

from backend.app.api import overview as overview_api
from backend.app.db.store import AppStateDB


def make_app(tmp_path: Path) -> tuple[Flask, AppStateDB]:
    app = Flask(__name__)
    state_db = AppStateDB(tmp_path / f"state-{uuid.uuid4().hex}.sqlite3")
    app.config["APP_STATE_DB"] = state_db
    app.register_blueprint(overview_api.bp)
    return app, state_db


def test_overview_counts_include_browser_and_llm(tmp_path):
    app, state_db = make_app(tmp_path)

    tab_id = "tab-ov"
    history_id = state_db.add_history_entry(
        tab_id=tab_id,
        url="https://example.com",
        title="Example",
        referrer=None,
        status_code=200,
        content_type="text/html",
    )
    assert history_id
    thread_id = state_db.create_llm_thread(title="Overview", origin="browser")
    state_db.bind_tab_thread(tab_id, thread_id)
    state_db.append_llm_message(thread_id=thread_id, role="user", content="hello")
    state_db.create_task(title="demo", thread_id=thread_id)
    state_db.upsert_memory(
        memory_id="mem-ov",
        scope="thread",
        scope_ref=thread_id,
        key="k",
        value="remember",
        metadata=None,
        strength=0.9,
        thread_id=thread_id,
        task_id=None,
        source_message_id=None,
        embedding_ref=None,
    )
    state_db.upsert_document(
        job_id=None,
        document_id="doc-ov",
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
            "INSERT OR IGNORE INTO pending_documents(doc_id, url) VALUES(?, ?)",
            ("pend-1", "https://example.com"),
        )
        state_db._conn.execute(
            "INSERT OR IGNORE INTO pending_chunks(doc_id, chunk_index, text) VALUES(?, ?, ?)",
            ("pend-1", 0, "chunk"),
        )
        state_db._conn.execute(
            "INSERT OR IGNORE INTO pending_vectors_queue(doc_id) VALUES(?)",
            ("pend-1",),
        )
        state_db._conn.execute(
            "INSERT OR IGNORE INTO pages(url, title) VALUES(?, ?)",
            ("https://example.com", "Example"),
        )

    client = app.test_client()
    resp = client.get("/api/overview")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["browser"]["tabs"]["total"] >= 1
    assert payload["llm"]["threads"]["total"] >= 1
    assert payload["knowledge"]["documents"] >= 1
    assert payload["storage"]
