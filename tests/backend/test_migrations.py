import os
import sqlite3
import tempfile

import pytest

from backend.app.db import schema


@pytest.mark.parametrize("passes", [1, 2])
def test_migrate_runs_without_error_multiple_times(passes: int) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "state.db")
        conn = sqlite3.connect(db_path)
        try:
            for _ in range(passes):
                schema.migrate(conn)

            cursor = conn.execute("SELECT id FROM _migrations ORDER BY id")
            applied = [row[0] for row in cursor.fetchall()]
            assert applied == list(schema.MIGRATION_IDS)
        finally:
            conn.close()


def test_crawl_jobs_priority_column_defaults_and_update() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "state.db")
        conn = sqlite3.connect(db_path)
        try:
            schema.migrate(conn)
            schema.migrate(conn)

            info = {
                row[1]: {
                    "type": row[2],
                    "notnull": row[3],
                    "default": row[4],
                }
                for row in conn.execute("PRAGMA table_info(crawl_jobs)")
            }

            priority = info["priority"]
            assert priority["type"].upper() == "INTEGER"
            assert priority["notnull"] == 1
            assert priority["default"] in {"0", 0}

            assert "enqueued_at" in info
            assert info["enqueued_at"]["default"] in (None, "")

            conn.execute(
                "INSERT INTO crawl_jobs(id, status) VALUES(?, ?)",
                ("job-1", "queued"),
            )
            conn.commit()
            row = conn.execute(
                "SELECT priority, enqueued_at FROM crawl_jobs WHERE id=?",
                ("job-1",),
            ).fetchone()
            assert row[0] == 0

            conn.execute(
                "UPDATE crawl_jobs SET priority = 5 WHERE id = ?",
                ("job-1",),
            )
            conn.commit()
            updated = conn.execute(
                "SELECT priority FROM crawl_jobs WHERE id=?",
                ("job-1",),
            ).fetchone()
            assert updated[0] == 5
        finally:
            conn.close()


def test_hydraflow_tables_and_columns_created() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "state.db")
        conn = sqlite3.connect(db_path)
        try:
            schema.migrate(conn)
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            for name in {"llm_threads", "llm_messages", "tasks", "task_events", "memory_embeddings"}:
                assert name in tables

            memories_columns = {row[1] for row in conn.execute("PRAGMA table_info(memories)")}
            for column in {"thread_id", "task_id", "source_message_id", "embedding_ref"}:
                assert column in memories_columns

            conn.execute(
                "INSERT INTO llm_threads(id, title, origin) VALUES(?, ?, ?)",
                ("thread-1", "Thread", "test"),
            )
            conn.execute(
                "INSERT INTO llm_messages(id, thread_id, role, content) VALUES(?, ?, 'user', 'hi')",
                ("msg-1", "thread-1"),
            )
            conn.commit()

            message = conn.execute(
                "SELECT thread_id FROM llm_messages WHERE id=?",
                ("msg-1",),
            ).fetchone()
            assert message[0] == "thread-1"
        finally:
            conn.close()
