from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace

from pathlib import Path
from types import SimpleNamespace

import duckdb
import pytest
from flask import Flask
from whoosh import index as whoosh_index
from whoosh.fields import ID, TEXT, Schema

from backend.app.services import index_health


@pytest.fixture
def app_context(tmp_path):
    app = Flask(__name__)
    sqlite_path = tmp_path / "app_state.sqlite3"
    duck_path = tmp_path / "vectors.duckdb"
    index_dir = tmp_path / "whoosh"
    last_index_path = tmp_path / "state" / "last.txt"
    last_index_path.parent.mkdir(parents=True, exist_ok=True)
    last_index_path.write_text("0")

    # Prepare sqlite documents table
    import sqlite3

    conn = sqlite3.connect(sqlite_path)
    conn.execute("CREATE TABLE documents(id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT)")
    conn.execute("INSERT INTO documents(url) VALUES('https://example.com')")
    conn.commit()
    conn.close()

    # Prepare duckdb documents table
    with duckdb.connect(str(duck_path)) as conn:
        conn.execute("CREATE TABLE documents(url VARCHAR)")
        conn.execute("INSERT INTO documents VALUES ('https://duckdb.example')")

    # Prepare Whoosh index
    index_dir.mkdir(parents=True, exist_ok=True)
    schema = Schema(url=ID(stored=True, unique=True), content=TEXT(stored=True))
    ix = whoosh_index.create_in(index_dir, schema)
    writer = ix.writer()
    writer.add_document(url="https://whoosh.example", content="hello world")
    writer.commit()

    vector_service = SimpleNamespace(
        metadata=lambda: {"documents": 3, "dimensions": 128},
        warmup=lambda attempts=1: None,
    )
    search_service = SimpleNamespace(reload_index=lambda: None)

    app.config.update(
        APP_CONFIG=SimpleNamespace(
            app_state_db_path=sqlite_path,
            agent_data_dir=tmp_path / "agent",
            index_dir=index_dir,
            last_index_time_path=last_index_path,
        ),
        VECTOR_INDEX_SERVICE=vector_service,
        SEARCH_SERVICE=search_service,
    )

    ctx = app.app_context()
    ctx.push()
    try:
        yield app
    finally:
        ctx.pop()


def test_probe_all_reports_stores(app_context):
    payload = index_health.probe_all()
    assert payload["status"] in {"green", "yellow", "red"}
    store_names = {store["name"] for store in payload["stores"]}
    assert "app_state" in store_names
    assert "vector_index" in store_names
    assert "vector_duckdb" in store_names
    assert "keyword_index" in store_names


def test_rebuild_updates_timestamp(app_context, monkeypatch):
    triggered = {
        "reload": False,
        "warmup": False,
    }

    def fake_thread(target, **_kwargs):
        class ImmediateThread:
            def start(self_inner):
                target()

        return ImmediateThread()

    monkeypatch.setattr(index_health.threading, "Thread", fake_thread)

    vector_service = app_context.config["VECTOR_INDEX_SERVICE"]
    search_service = app_context.config["SEARCH_SERVICE"]
    vector_service.warmup = lambda attempts=1: triggered.update({"warmup": True})
    search_service.reload_index = lambda: triggered.update({"reload": True})

    result = index_health.rebuild()
    assert result["accepted"] is True
    assert triggered["warmup"] is True
    assert triggered["reload"] is True
    marker = Path(app_context.config["APP_CONFIG"].last_index_time_path)
    assert marker.exists()
    assert marker.read_text().strip() != "0"
