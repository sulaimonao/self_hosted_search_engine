from pathlib import Path

from flask import Flask

from backend.app.api import chat as chat_api
from backend.app.api.schemas import ChatRequest
from backend.app.db.store import AppStateDB


def make_app(tmp_path: Path) -> tuple[Flask, AppStateDB]:
    app = Flask(__name__)
    state_db = AppStateDB(tmp_path / "state.sqlite3")
    app.config["APP_STATE_DB"] = state_db
    return app, state_db


def _chat_request(**kwargs) -> ChatRequest:
    base = {"messages": [{"role": "user", "content": "hi"}]}
    base.update(kwargs)
    return ChatRequest.model_validate(base)


def test_tab_binding_reuses_existing_thread(tmp_path):
    app, state_db = make_app(tmp_path)
    thread_id = state_db.create_llm_thread(title="Browser", origin="browser")
    state_db.bind_tab_thread("tab-1", thread_id)

    with app.test_request_context("/api/chat/stream", json={}):
        resolved = chat_api._ensure_thread_context(_chat_request(tab_id="tab-1"))
        assert resolved == thread_id
        assert state_db.tab_thread_id("tab-1") == thread_id


def test_tab_binding_creates_and_links_thread(tmp_path):
    app, state_db = make_app(tmp_path)

    with app.test_request_context("/api/chat/stream", json={}):
        req = _chat_request(tab_id="tab-2", request_id="req-123")
        resolved = chat_api._ensure_thread_context(req)
        assert resolved == "req-123"
        assert state_db.tab_thread_id("tab-2") == "req-123"
