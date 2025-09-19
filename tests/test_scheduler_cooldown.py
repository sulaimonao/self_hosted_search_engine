from __future__ import annotations

import types

from backend.app.config import AppConfig
from backend.app.jobs.focused_crawl import FocusedCrawlSupervisor


class DummyProcess:
    def __init__(self, *args, **kwargs) -> None:
        self._returncode = 0

    def poll(self):
        return None

    def wait(self):
        return 0


def noop_thread(*args, **kwargs):
    return types.SimpleNamespace(start=lambda: None)


def test_scheduler_respects_cooldown(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("FOCUSED_CRAWL_ENABLED", "1")
    monkeypatch.setenv("SMART_TRIGGER_COOLDOWN", "120")

    config = AppConfig.from_env()
    config.ensure_dirs()
    supervisor = FocusedCrawlSupervisor(config)

    monkeypatch.setattr("backend.app.jobs.focused_crawl.subprocess.Popen", lambda *a, **k: DummyProcess())
    monkeypatch.setattr("backend.app.jobs.focused_crawl.normalize", lambda *a, **k: [])
    monkeypatch.setattr("backend.app.jobs.focused_crawl.incremental_index", lambda *a, **k: (0, 0, 0))
    monkeypatch.setattr("backend.app.jobs.focused_crawl.threading.Thread", noop_thread)

    assert supervisor.schedule("sample query", use_llm=False, model=None)

    if supervisor._current:
        supervisor._current.log_handle.close()
        supervisor._current = None

    assert not supervisor.schedule("sample query", use_llm=False, model=None)
