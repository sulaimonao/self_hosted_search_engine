from __future__ import annotations

import time

import pytest

from backend.app import create_app


def test_diagnostics_requires_json_object():
    app = create_app()
    client = app.test_client()

    response = client.post("/api/diagnostics", json=["nope"])
    assert response.status_code == 400
    assert response.get_json()["error"]


def test_diagnostics_rejects_non_boolean_flag():
    app = create_app()
    client = app.test_client()

    response = client.post("/api/diagnostics", json={"include_pytest": "yes"})
    assert response.status_code == 400
    assert "boolean" in response.get_json()["error"]


def test_diagnostics_job_execution(monkeypatch: pytest.MonkeyPatch):
    app = create_app()
    client = app.test_client()

    calls: list[tuple[object, object]] = []

    def fake_run(config, include_pytest=None):
        calls.append((config, include_pytest))
        return {
            "generated_at": "2024-01-01T00:00:00Z",
            "repo": {"head": "abc123"},
            "tests": {"enabled": False},
            "dependencies": {"packages": {}},
            "logs": [],
            "summary_path": "/tmp/diag.md",
            "summary_markdown": "# diagnostics",
        }

    monkeypatch.setattr("backend.app.api.diagnostics.run_diagnostics", fake_run)

    response = client.post("/api/diagnostics", json={"include_pytest": True})
    assert response.status_code == 200
    payload = response.get_json()
    job_id = payload["job_id"]
    assert isinstance(job_id, str)

    deadline = time.time() + 2
    final = None
    while time.time() < deadline:
        status_resp = client.get(f"/api/jobs/{job_id}/status")
        assert status_resp.status_code == 200
        job_info = status_resp.get_json()
        if job_info.get("state") == "done":
            final = job_info
            break
        time.sleep(0.05)

    assert final is not None, "diagnostics job did not finish in time"
    result = final.get("result")
    assert result["summary_path"] == "/tmp/diag.md"
    assert result["summary_markdown"].startswith("# diagnostics")
    assert calls and calls[0][1] is True

