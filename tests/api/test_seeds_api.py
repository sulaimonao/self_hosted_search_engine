from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from flask import Flask

from backend.app.api.seeds import bp as seeds_bp


def _write_registry(path: Path) -> None:
    payload = {
        "version": 1,
        "crawl_defaults": {"strategy": "crawl"},
        "directories": {
            "news": {
                "sources": [
                    {
                        "id": "news_ap_top",
                        "entrypoints": ["https://news.example.com/feed"],
                        "scope": "domain",
                    }
                ]
            },
            "workspace": {
                "sources": [
                    {
                        "id": "workspace-seed",
                        "entrypoints": ["https://workspace.example.com"],
                        "scope": "page",
                        "notes": "Starter",
                    }
                ]
            },
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


@pytest.fixture()
def app(tmp_path: Path) -> Flask:
    registry_path = tmp_path / "registry.yaml"
    _write_registry(registry_path)
    app = Flask(__name__)
    app.register_blueprint(seeds_bp)
    app.testing = True
    app.config.update(SEED_REGISTRY_PATH=registry_path, SEED_WORKSPACE_DIRECTORY="workspace")
    return app


def test_list_seeds_returns_revision_and_entries(app: Flask) -> None:
    client = app.test_client()
    response = client.get("/api/seeds")
    assert response.status_code == 200
    payload = response.get_json()
    assert isinstance(payload, dict)
    assert isinstance(payload.get("revision"), str)
    seeds = payload.get("seeds")
    assert isinstance(seeds, list)
    directories = {seed["directory"] for seed in seeds}
    assert "news" in directories
    assert "workspace" in directories
    workspace_seed = next(seed for seed in seeds if seed["directory"] == "workspace")
    assert workspace_seed["editable"] is True
    assert workspace_seed["url"] == "https://workspace.example.com"


def test_create_seed_requires_matching_revision(app: Flask) -> None:
    client = app.test_client()
    initial = client.get("/api/seeds").get_json()
    revision = initial["revision"]

    create_response = client.post(
        "/api/seeds",
        json={
            "revision": revision,
            "url": "https://docs.example.com",
            "scope": "domain",
            "notes": "Docs",
        },
    )
    assert create_response.status_code == 201
    created = create_response.get_json()
    assert created["revision"] != revision
    workspace_urls = [seed["url"] for seed in created["seeds"] if seed["directory"] == "workspace"]
    assert "https://docs.example.com" in workspace_urls

    conflict = client.post(
        "/api/seeds",
        json={
            "revision": revision,
            "url": "https://docs.example.com/again",
            "scope": "page",
        },
    )
    assert conflict.status_code == 409
    conflict_body = conflict.get_json()
    assert "revision" in conflict_body


def test_update_and_delete_seed(app: Flask) -> None:
    client = app.test_client()
    initial = client.get("/api/seeds").get_json()
    revision = initial["revision"]

    update_response = client.put(
        "/api/seeds/workspace-seed",
        json={"revision": revision, "scope": "domain"},
    )
    assert update_response.status_code == 200
    updated = update_response.get_json()
    workspace_seed = next(seed for seed in updated["seeds"] if seed["id"] == "workspace-seed")
    assert workspace_seed["scope"] == "domain"
    new_revision = updated["revision"]

    delete_conflict = client.delete(
        "/api/seeds/workspace-seed",
        json={"revision": revision},
    )
    assert delete_conflict.status_code == 409

    delete_response = client.delete(
        "/api/seeds/workspace-seed",
        json={"revision": new_revision},
    )
    assert delete_response.status_code == 200
    remaining = delete_response.get_json()["seeds"]
    assert all(seed["id"] != "workspace-seed" for seed in remaining)
