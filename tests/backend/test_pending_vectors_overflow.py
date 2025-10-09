from __future__ import annotations

import hashlib
import sqlite3
import time
from pathlib import Path

import pytest

from backend.app.db.store import AppStateDB


@pytest.fixture()
def temp_state_db(tmp_path: Path) -> AppStateDB:
    db_path = tmp_path / "app_state.sqlite3"
    return AppStateDB(db_path)


def test_enqueue_handles_large_identifiers(temp_state_db: AppStateDB) -> None:
    store = temp_state_db
    big_job_id = str(2**130)
    doc_hash = hashlib.sha256(b"overflow-check").hexdigest()
    sim_signature = 2**63 + 12345
    doc_id = f"doc-{hashlib.sha1(b'unique').hexdigest()}"

    store.enqueue_pending_document(
        doc_id=doc_id,
        job_id=big_job_id,
        url="https://example.com/article",
        title="Article",
        resolved_title="Resolved Title",
        doc_hash=doc_hash,
        sim_signature=sim_signature,
        metadata={"source": "test"},
        chunks=[(0, "chunk body", {"start": 0, "end": 12, "token_count": 3})],
        initial_delay=0.0,
    )

    diag = store.schema_diagnostics(refresh=True)
    assert diag["ok"], diag["errors"]
    tables = diag["tables"].get("pending_documents", {})
    assert tables.get("job_id") == "TEXT"
    assert tables.get("doc_hash") == "TEXT"
    assert tables.get("sim_signature") == "TEXT"
    assert tables.get("created_at") == "INTEGER"

    conn = sqlite3.connect(store.path)
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT job_id, doc_hash, sim_signature, created_at FROM pending_documents WHERE doc_id = ?",
            (doc_id,),
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row["job_id"] == big_job_id
    assert row["doc_hash"] == doc_hash
    assert row["sim_signature"] == str(sim_signature)
    assert isinstance(row["created_at"], int)
    assert 0 < row["created_at"] <= int(time.time())

    pending = store.pop_pending_documents(limit=1)
    assert pending and pending[0]["doc_id"] == doc_id
    record = pending[0]
    assert record["job_id"] == big_job_id
    assert record["doc_hash"] == doc_hash
    assert record["sim_signature"] == sim_signature
    assert record["attempts"] == 0
    assert record["chunks"] and record["chunks"][0]["text"] == "chunk body"
