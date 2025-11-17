from flask import Flask

from backend.app.api import jobs as jobs_api
from backend.app.db.store import AppStateDB


def test_jobs_table_endpoints(tmp_path):
    db_path = tmp_path / "jobs-state.sqlite3"
    state_db = AppStateDB(db_path)
    job_id = state_db.create_job("bundle_export")
    state_db.update_job(job_id, status="running")
    app = Flask(__name__)
    app.config["APP_STATE_DB"] = state_db
    app.register_blueprint(jobs_api.bp)
    client = app.test_client()
    list_resp = client.get("/api/jobs?status=running")
    assert list_resp.status_code == 200
    items = list_resp.get_json()["items"]
    assert any(item["id"] == job_id for item in items)
    detail = client.get(f"/api/jobs/{job_id}")
    assert detail.status_code == 200
    payload = detail.get_json()["job"]
    assert payload["status"] == "running"
    missing = client.get("/api/jobs/does-not-exist")
    assert missing.status_code == 404
