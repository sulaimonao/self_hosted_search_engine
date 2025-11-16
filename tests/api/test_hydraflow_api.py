from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from flask import Flask

from backend.app.api import chat_history as chat_history_api
from backend.app.api import hydraflow as hydraflow_api
from backend.app.db.store import AppStateDB


@pytest.fixture()
def app_client(tmp_path):
    db_path = tmp_path / f"state-{uuid.uuid4().hex}.sqlite3"
    app = Flask(__name__)
    state_db = AppStateDB(Path(db_path))
    app.config["APP_STATE_DB"] = state_db
    app.register_blueprint(hydraflow_api.bp)
    app.register_blueprint(chat_history_api.bp)
    client = app.test_client()
    return app, client


def test_thread_message_and_memory_flow(app_client):
    app, client = app_client

    # Create a thread via API
    resp = client.post(
        "/api/threads",
        json={"title": "Hydra", "description": "demo", "metadata": {"source": "test"}},
    )
    assert resp.status_code == 201
    payload = resp.get_json()
    thread_id = payload["id"]
    assert payload["thread"]["title"] == "Hydra"

    # Append a message via the new endpoint
    msg_resp = client.post(
        f"/api/threads/{thread_id}/messages",
        json={"role": "user", "content": "hello world", "metadata": {"kind": "test"}},
    )
    assert msg_resp.status_code == 201
    message_id = msg_resp.get_json()["id"]

    # Store a legacy chat message to ensure compatibility writes through
    legacy_resp = client.post(
        f"/api/chat/{thread_id}/message",
        json={"role": "assistant", "content": "ack"},
    )
    assert legacy_resp.status_code == 200

    messages = client.get(f"/api/threads/{thread_id}/messages")
    assert messages.status_code == 200
    items = messages.get_json()["items"]
    roles = [item["role"] for item in items]
    assert "user" in roles and "assistant" in roles
    assert any(item["id"] == message_id for item in items)

    # Upsert a memory linked to the thread
    mem_resp = client.post(
        "/api/memories/upsert",
        json={
            "id": "mem-1",
            "scope": "thread",
            "scope_ref": thread_id,
            "value": "A greeting happened",
            "thread_id": thread_id,
        },
    )
    assert mem_resp.status_code == 200

    search_resp = client.post(
        "/api/memories/search",
        json={"scope": "thread", "scope_ref": thread_id, "query": "greeting"},
    )
    assert search_resp.status_code == 200
    assert any(item["id"] == "mem-1" for item in search_resp.get_json()["items"])


def test_task_crud_and_events(app_client):
    app, client = app_client
    thread_resp = client.post("/api/threads", json={"title": "Tasks"})
    thread_id = thread_resp.get_json()["id"]

    task_resp = client.post(
        "/api/tasks",
        json={
            "title": "plan",
            "thread_id": thread_id,
            "priority": 2,
            "metadata": {"kind": "demo"},
        },
    )
    assert task_resp.status_code == 201
    task_payload = task_resp.get_json()
    task_id = task_payload["id"]
    assert task_payload["task"]["thread_id"] == thread_id

    list_resp = client.get("/api/tasks")
    assert list_resp.status_code == 200
    assert any(item["id"] == task_id for item in list_resp.get_json()["items"])

    patch_resp = client.patch(
        f"/api/tasks/{task_id}",
        json={"status": "in_progress", "owner": "bot", "result": {"ok": True}},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.get_json()["task"]["status"] == "in_progress"

    event_resp = client.post(
        f"/api/tasks/{task_id}/events",
        json={"event_type": "note", "payload": {"detail": "started"}},
    )
    assert event_resp.status_code == 201

    events = client.get(f"/api/tasks/{task_id}/events")
    assert events.status_code == 200
    assert any(evt["event_type"] == "note" for evt in events.get_json()["items"])
