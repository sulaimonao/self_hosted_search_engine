import subprocess

import pytest
from flask import Flask

from backend.app.api import repo as repo_api
from backend.app.db.store import AppStateDB
from scripts import change_budget


@pytest.fixture()
def app_client(tmp_path):
    db_path = tmp_path / "state.sqlite3"
    state_db = AppStateDB(db_path)
    app = Flask(__name__)
    app.config["APP_STATE_DB"] = state_db
    app.register_blueprint(repo_api.bp)
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_dir, check=True)
    (repo_dir / "README.md").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo_dir, check=True, capture_output=True)
    state_db.register_repo("demo", root_path=repo_dir, allowed_ops=["read", "write"])
    return app.test_client(), state_db, repo_dir


def test_repo_list_and_status(app_client):
    client, _db, repo_dir = app_client
    listing = client.get("/api/repo/list")
    assert listing.status_code == 200
    payload = listing.get_json()
    assert any(item["id"] == "demo" for item in payload["items"])
    status = client.get("/api/repo/demo/status")
    assert status.status_code == 200
    summary = status.get_json()
    assert summary["root_path"] == str(repo_dir)


def test_propose_patch_respects_budget(app_client):
    client, _db, _repo_dir = app_client
    ok_resp = client.post(
        "/api/repo/demo/propose_patch",
        json={
            "files": [
                {
                    "path": "README.md",
                    "diff": "--- a/README.md\n+++ b/README.md\n+extra\n",
                }
            ]
        },
    )
    assert ok_resp.status_code == 202
    reject_resp = client.post(
        "/api/repo/demo/propose_patch",
        json={
            "files": [
                {
                    "path": "README.md",
                    "additions": change_budget.MAX_LOC + 1,
                }
            ]
        },
    )
    assert reject_resp.status_code == 400
    detail = reject_resp.get_json()
    assert detail["error"] == "budget_exceeded"


def test_propose_requires_files(app_client):
    client, _db, _repo_dir = app_client
    resp = client.post("/api/repo/demo/propose_patch", json={})
    assert resp.status_code == 400
