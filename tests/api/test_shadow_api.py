from __future__ import annotations

from backend.app import create_app


class DummyShadowManager:
    def __init__(self) -> None:
        self.enqueued: list[tuple[str, int | None, str | None]] = []
        self.enabled = False
        self.jobs: dict[str, dict[str, object]] = {
            "job-123": {
                "jobId": "job-123",
                "url": "https://example.com",
                "state": "done",
                "phase": "indexed",
                "title": "Example",
                "chunks": 5,
                "docs": [{"id": "doc-1", "title": "Example", "tokens": 128}],
                "errors": [],
                "metrics": {"fetch_ms": 10.0},
            }
        }

    def enqueue(self, url: str, tab_id: int | None = None, reason: str | None = None):
        self.enqueued.append((url, tab_id, reason))
        return {
            "jobId": "job-123",
            "url": url,
            "state": "queued",
            "phase": "queued",
            "docs": [],
            "errors": [],
            "metrics": {},
        }

    def job_status(self, job_id: str):
        return self.jobs.get(job_id)

    def status_by_url(self, url: str):
        if url == "https://example.com":
            return self.jobs["job-123"]
        return {"url": url, "state": "idle", "phase": "idle", "docs": [], "errors": [], "metrics": {}, "jobId": None}

    def get_config(self):
        return {"enabled": self.enabled, "queued": len(self.enqueued), "running": 0}

    def set_enabled(self, enabled: bool):
        self.enabled = bool(enabled)
        return self.get_config()

    def toggle(self):
        self.enabled = not self.enabled
        return self.get_config()


def test_shadow_queue_and_status():
    app = create_app()
    manager = DummyShadowManager()
    app.config["SHADOW_INDEX_MANAGER"] = manager

    client = app.test_client()

    missing = client.post("/api/shadow/crawl", json={})
    assert missing.status_code == 400

    response = client.post("/api/shadow/crawl", json={"url": "https://example.com", "tabId": 7})
    assert response.status_code == 202
    data = response.get_json()
    assert data["state"] == "queued"
    assert data["jobId"] == "job-123"
    assert manager.enqueued == [("https://example.com", 7, None)]

    # legacy endpoint remains functional
    legacy = client.post("/api/shadow/queue", json={"url": "https://example.com"})
    assert legacy.status_code == 202

    status = client.get("/api/shadow/status", query_string={"jobId": "job-123"})
    assert status.status_code == 200
    status_data = status.get_json()
    assert status_data["state"] == "done"
    assert status_data["title"] == "Example"
    assert status_data["chunks"] == 5
    assert status_data["docs"]

    missing_status = client.get("/api/shadow/status")
    assert missing_status.status_code == 400

    toggle = client.post("/api/shadow/toggle")
    assert toggle.status_code == 200
    toggle_data = toggle.get_json()
    assert toggle_data["enabled"] is True
    toggle_again = client.post("/api/shadow/toggle")
    assert toggle_again.status_code == 200
    assert toggle_again.get_json()["enabled"] is False
