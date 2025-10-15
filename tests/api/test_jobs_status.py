from __future__ import annotations

import time

from app import create_app


class _StubRefreshWorker:
    """Refresh worker replacement returning malformed status payloads."""

    def status(self, *, job_id: str | None = None, query: str | None = None) -> object:
        return None


def test_job_status_handles_non_mapping_refresh_worker() -> None:
    app = create_app()
    runner = app.config["JOB_RUNNER"]

    job_id = runner.submit(lambda: "done")
    for _ in range(50):
        snapshot = runner.status(job_id)
        if snapshot.get("state") == "done":
            break
        time.sleep(0.1)

    app.config["REFRESH_WORKER"] = _StubRefreshWorker()

    client = app.test_client()
    response = client.get(f"/api/jobs/{job_id}/status")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload.get("state") == "done"
