from __future__ import annotations

from pathlib import Path

import pytest

from backend.app import create_app


@pytest.fixture()
def repo_app(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    db_path = tmp_path / "state.sqlite3"
    monkeypatch.setenv("APP_STATE_DB_PATH", str(db_path))
    app = create_app()
    return app


def test_apply_patch_rejects_path_traversal(repo_app, tmp_path: Path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    state_db = repo_app.config["APP_STATE_DB"]
    state_db.register_repo("sample", root_path=repo_root, allowed_ops=["write"])
    client = repo_app.test_client()
    response = client.post(
        "/api/repo/sample/apply_patch",
        json={"files": [{"path": "../outside.txt", "content": "bad"}]},
    )
    assert response.status_code == 400
    assert not (repo_root.parent / "outside.txt").exists()


def test_run_checks_requires_configured_command(repo_app, tmp_path: Path):
    repo_root = tmp_path / "repo2"
    repo_root.mkdir()
    state_db = repo_app.config["APP_STATE_DB"]
    state_db.register_repo("sample", root_path=repo_root, allowed_ops=["run_checks"])
    client = repo_app.test_client()
    response = client.post("/api/repo/sample/run_checks", json={})
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["error"] == "no check command configured for this repository"


def test_run_checks_rejects_override(repo_app, tmp_path: Path):
    repo_root = tmp_path / "repo3"
    repo_root.mkdir()
    state_db = repo_app.config["APP_STATE_DB"]
    state_db.register_repo(
        "sample",
        root_path=repo_root,
        allowed_ops=["run_checks"],
        check_command=["/bin/echo", "ok"],
    )
    client = repo_app.test_client()
    response = client.post(
        "/api/repo/sample/run_checks",
        json={"command": ["/bin/false"]},
    )
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["error"] == "command_not_allowed"
