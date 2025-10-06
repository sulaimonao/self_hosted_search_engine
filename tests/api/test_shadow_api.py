from __future__ import annotations

from backend.app import create_app


class DummyShadowManager:
    def __init__(self) -> None:
        self.enqueued: list[str] = []
        self.enabled = False

    def enqueue(self, url: str):
        self.enqueued.append(url)
        return {"url": url, "state": "queued", "job_id": "job-123"}

    def status(self, url: str):
        return {
            "url": url,
            "state": "done",
            "job_id": "job-123",
            "title": "Example",
            "chunks": 5,
        }

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

    missing = client.post("/api/shadow/queue", json={})
    assert missing.status_code == 400

    response = client.post("/api/shadow/queue", json={"url": "https://example.com"})
    assert response.status_code == 202
    data = response.get_json()
    assert data["state"] == "queued"
    assert data["job_id"] == "job-123"
    assert manager.enqueued == ["https://example.com"]

    status = client.get(
        "/api/shadow/status", query_string={"url": "https://example.com"}
    )
    assert status.status_code == 200
    status_data = status.get_json()
    assert status_data["state"] == "done"
    assert status_data["title"] == "Example"
    assert status_data["chunks"] == 5

    missing_status = client.get("/api/shadow/status")
    assert missing_status.status_code == 400

    toggle = client.post("/api/shadow/toggle")
    assert toggle.status_code == 200
    toggle_data = toggle.get_json()
    assert toggle_data["enabled"] is True
    toggle_again = client.post("/api/shadow/toggle")
    assert toggle_again.status_code == 200
    assert toggle_again.get_json()["enabled"] is False
