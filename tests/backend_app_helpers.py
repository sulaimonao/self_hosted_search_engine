from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable

from flask import Flask

from backend.app.config import AppConfig
from backend.app.db.store import AppStateDB


class _DummyJobRunner:
    """Minimal job runner stub for API tests."""

    def status(self, job_id: str):  # noqa: D401 - compatibility shim
        return {}

    def log_path(self, job_id: str):  # noqa: D401 - compatibility shim
        return None


def build_test_app(
    tmp_path: Path,
    monkeypatch,
    *,
    blueprints: Iterable,
) -> tuple[Flask, AppStateDB, AppConfig]:
    """Create a Flask app with the requested blueprints and temp config."""

    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    config = AppConfig.from_env()
    state_db = AppStateDB(tmp_path / "state.sqlite3")
    app = Flask(__name__)
    app.config.update(
        APP_CONFIG=config,
        APP_STATE_DB=state_db,
        CHAT_LOGGER=logging.getLogger("test.chat"),
        JOB_RUNNER=_DummyJobRunner(),
        REFRESH_WORKER=None,
    )
    for bp in blueprints:
        app.register_blueprint(bp)
    return app, state_db, config
