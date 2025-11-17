from __future__ import annotations

from pathlib import Path

import pytest

from backend.app import create_app


@pytest.fixture()
def hydraflow_app(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    db_path = tmp_path / "state.sqlite3"
    monkeypatch.setenv("APP_STATE_DB_PATH", str(db_path))
    app = create_app()
    return app


def test_delete_thread_cascades(hydraflow_app):
    state_db = hydraflow_app.config["APP_STATE_DB"]
    thread_id = state_db.create_llm_thread(title="demo")
    state_db.append_llm_message(thread_id=thread_id, role="user", content="hi")
    state_db.create_task(thread_id=thread_id, title="Task")
    state_db.upsert_memory(
        memory_id="mem1",
        scope="thread",
        scope_ref=thread_id,
        key="summary",
        value="memory",
        metadata=None,
        strength=0.5,
        thread_id=thread_id,
    )
    state_db.bind_tab_thread("tab-1", thread_id)
    client = hydraflow_app.test_client()
    response = client.delete(f"/api/threads/{thread_id}")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["stats"]["threads"] == 1
    assert state_db.get_llm_thread(thread_id) is None
    assert state_db.list_llm_messages(thread_id) == []
    assert state_db.list_tasks(thread_id=thread_id) == []
    assert state_db.search_memories(scope="hydraflow", scope_ref=thread_id) == []
