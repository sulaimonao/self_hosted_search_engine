from pathlib import Path

from pathlib import Path

from flask import Flask

from backend.app.api import bundle as bundle_api
from backend.app.api import jobs as jobs_api
from backend.app.db.store import AppStateDB


def _make_app(db_path: Path, bundle_dir: Path) -> tuple[Flask, AppStateDB]:
    app = Flask(__name__)
    state_db = AppStateDB(db_path)
    app.config["APP_STATE_DB"] = state_db
    app.config["BUNDLE_STORAGE_DIR"] = bundle_dir
    app.register_blueprint(bundle_api.bp)
    app.register_blueprint(jobs_api.bp)
    return app, state_db


def test_export_and_import_bundle_round_trip(tmp_path):
    bundle_dir = tmp_path / "bundles"
    export_db = tmp_path / "state-export.sqlite3"
    export_app, export_state = _make_app(export_db, bundle_dir)
    thread_id = export_state.create_llm_thread(title="Demo", description="test")
    export_state.append_llm_message(thread_id=thread_id, role="user", content="hello")
    export_state.create_task(title="todo", thread_id=thread_id)
    export_state.add_history_entry(tab_id="tab-1", url="https://example.com", title="Example")
    export_client = export_app.test_client()
    export_resp = export_client.get("/api/export/bundle")
    assert export_resp.status_code == 200
    export_payload = export_resp.get_json()
    bundle_path = Path(export_payload["bundle_path"])
    assert bundle_path.exists()
    job_record = export_state.get_job(export_payload["job_id"])
    assert job_record["status"] == "succeeded"
    assert "browser_history" in export_payload["manifest"]["included_components"]

    import_db = tmp_path / "state-import.sqlite3"
    import_app, import_state = _make_app(import_db, bundle_dir)
    import_client = import_app.test_client()
    import_resp = import_client.post(
        "/api/import/bundle",
        json={"bundle_path": str(bundle_path)},
    )
    assert import_resp.status_code == 200
    import_payload = import_resp.get_json()
    assert import_payload["imported"]["threads"] >= 1
    imported_threads = import_state.list_llm_threads(limit=10)
    assert any(item["title"] == "Demo" for item in imported_threads)
    history_rows = import_state.query_history(limit=10)
    assert len(history_rows) == 1
    assert history_rows[0]["url"] == "https://example.com"

    second_import = import_client.post(
        "/api/import/bundle",
        json={"bundle_path": str(bundle_path)},
    )
    assert second_import.status_code == 200
    history_after = import_state.query_history(limit=10)
    assert len(history_after) == 1
