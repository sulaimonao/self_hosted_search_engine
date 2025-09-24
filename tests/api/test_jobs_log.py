"""Tests for the job log download endpoint."""

from __future__ import annotations

import time

from app import create_app


def test_job_log_endpoint_unknown_job() -> None:
    app = create_app()
    client = app.test_client()
    response = client.get("/api/jobs/does-not-exist/log")
    assert response.status_code == 404
    payload = response.get_json()
    assert payload == {"error": "Log not found"}


def test_job_log_endpoint_downloads_completed_job() -> None:
    app = create_app()
    runner = app.config["JOB_RUNNER"]

    def _job() -> str:
        print("hello from job")  # pragma: no cover - exercised via log file
        return "done"

    job_id = runner.submit(_job)
    for _ in range(50):
        status = runner.status(job_id)
        if status.get("state") == "done":
            break
        time.sleep(0.1)

    client = app.test_client()
    response = client.get(f"/api/jobs/{job_id}/log?download=1")
    assert response.status_code == 200
    assert response.mimetype == "text/plain"
    assert "attachment;" in response.headers.get("Content-Disposition", "")
    assert b"hello from job" in response.data
