from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.app import create_app


@pytest.fixture()
def jobs_app(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    db_path = tmp_path / "state.sqlite3"
    monkeypatch.setenv("APP_STATE_DB_PATH", str(db_path))
    app = create_app()
    return app


def test_prune_jobs_removes_old_successes(jobs_app):
    state_db = jobs_app.config["APP_STATE_DB"]
    recent_id = state_db.create_job("demo", status="succeeded")
    old_id = state_db.create_job("demo", status="succeeded")
    stale_time = (datetime.now(tz=timezone.utc) - timedelta(days=10)).isoformat(timespec="seconds")
    state_db.update_job(old_id, completed_at=stale_time, status="succeeded")
    state_db.upsert_job_status(
        old_id,
        url=None,
        phase="done",
        steps_total=1,
        steps_completed=1,
        retries=0,
        eta_seconds=None,
        message="done",
        started_at=None,
    )
    client = jobs_app.test_client()
    response = client.delete(
        "/api/jobs",
        query_string={"older_than_days": 5, "status": "succeeded"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["deleted"] == 1
    assert state_db.get_job(old_id) is None
    assert state_db.get_job(recent_id) is not None
    assert state_db.get_job_status(old_id) is None
