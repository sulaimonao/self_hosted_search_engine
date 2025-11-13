from __future__ import annotations

import sys
import uuid
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from flask import Flask


class _DuckDBConnection:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, *args, **kwargs):
        return self

    def fetchone(self):
        return None

    def fetchall(self):
        return []


class _DuckDBStub(SimpleNamespace):
    def connect(self, *args, **kwargs):
        return _DuckDBConnection()


try:  # pragma: no cover - exercised indirectly during collection
    import duckdb  # type: ignore  # noqa: F401
except ModuleNotFoundError:
    if "duckdb" not in sys.modules:
        sys.modules["duckdb"] = _DuckDBStub()


class _FakeEncoding:
    def encode(self, text: str) -> list[int]:
        return [ord(ch) for ch in text]

    def decode(self, tokens: list[int]) -> str:
        return "".join(chr(int(token)) for token in tokens)


class _TiktokenStub(SimpleNamespace):
    def get_encoding(self, _name: str) -> _FakeEncoding:
        return _FakeEncoding()


try:  # pragma: no cover
    import tiktoken  # type: ignore  # noqa: F401
except ModuleNotFoundError:
    if "tiktoken" not in sys.modules:
        sys.modules["tiktoken"] = _TiktokenStub()


class _BeautifulSoupStub:
    def __init__(self, *args, **kwargs):
        self._html = args[0] if args else ""

    def __call__(self, *args, **kwargs):
        return []

    def select(self, *args, **kwargs):
        return []

    def find(self, *args, **kwargs):
        return None

    def find_all(self, *args, **kwargs):
        return []

    def get_text(self, *args, **kwargs):
        return self._html


try:  # pragma: no cover
    import bs4  # type: ignore  # noqa: F401
except ModuleNotFoundError:
    if "bs4" not in sys.modules:
        sys.modules["bs4"] = SimpleNamespace(BeautifulSoup=_BeautifulSoupStub)


def _trafilatura_extract(html: str, **_kwargs) -> str:
    return ""


try:  # pragma: no cover
    import trafilatura  # type: ignore  # noqa: F401
except ModuleNotFoundError:
    if "trafilatura" not in sys.modules:
        sys.modules["trafilatura"] = SimpleNamespace(extract=_trafilatura_extract)


class _PlaywrightBrowser(SimpleNamespace):
    def launch(self, *args, **kwargs):
        return SimpleNamespace(close=lambda: None)


class _PlaywrightClient(SimpleNamespace):
    def __init__(self):
        super().__init__(chromium=_PlaywrightBrowser())

    def stop(self):
        pass


class _SyncPlaywrightStub:
    def __enter__(self):
        return _PlaywrightClient()

    def __exit__(self, exc_type, exc, tb):
        return False

    def start(self):
        return _PlaywrightClient()


def _sync_playwright():
    return _SyncPlaywrightStub()


try:  # pragma: no cover
    from playwright import sync_api as _playwright_sync_api  # type: ignore  # noqa: F401
except (ModuleNotFoundError, ImportError):
    if "playwright.sync_api" not in sys.modules:
        sync_api_module = ModuleType("playwright.sync_api")
        sync_api_module.Error = RuntimeError
        sync_api_module.TimeoutError = RuntimeError
        sync_api_module.sync_playwright = _sync_playwright
        sys.modules["playwright.sync_api"] = sync_api_module
        playwright_module = ModuleType("playwright")
        playwright_module.sync_api = sync_api_module
        sys.modules["playwright"] = playwright_module


def _pdf_extract_text(*_args, **_kwargs) -> str:
    return ""


try:  # pragma: no cover
    import pdfminer.high_level  # type: ignore  # noqa: F401
except ModuleNotFoundError:
    if "pdfminer.high_level" not in sys.modules:
        pdf_high_level = ModuleType("pdfminer.high_level")
        pdf_high_level.extract_text = _pdf_extract_text
        sys.modules["pdfminer.high_level"] = pdf_high_level
        pdfminer_module = ModuleType("pdfminer")
        pdfminer_module.high_level = pdf_high_level
        sys.modules["pdfminer"] = pdfminer_module


def _httpx_get(*_args, **_kwargs):
    raise RuntimeError("httpx unavailable in tests")


try:  # pragma: no cover
    import httpx  # type: ignore  # noqa: F401
except ModuleNotFoundError:
    if "httpx" not in sys.modules:
        httpx_module = ModuleType("httpx")
        httpx_module.HTTPError = Exception
        httpx_module.get = _httpx_get
        httpx_module.post = _httpx_get
        sys.modules["httpx"] = httpx_module


class _FileSystemEvent:
    src_path: str = ""


class _FileSystemEventHandler:
    def on_created(self, *args, **kwargs):
        return None

    def on_modified(self, *args, **kwargs):
        return None


_watchdog_module = sys.modules.get("watchdog")
if _watchdog_module is None:
    _watchdog_module = ModuleType("watchdog")
    sys.modules["watchdog"] = _watchdog_module

try:  # pragma: no cover
    import watchdog.events  # type: ignore  # noqa: F401
except ModuleNotFoundError:
    if "watchdog.events" not in sys.modules:
        watchdog_events = ModuleType("watchdog.events")
        watchdog_events.FileSystemEvent = _FileSystemEvent
        watchdog_events.FileSystemEventHandler = _FileSystemEventHandler
        sys.modules["watchdog.events"] = watchdog_events
        _watchdog_module.events = watchdog_events


class _Observer:
    def schedule(self, *args, **kwargs):
        return None

    def start(self):
        return None

    def stop(self):
        return None

    def join(self, *args, **kwargs):
        return None


try:  # pragma: no cover
    import watchdog.observers  # type: ignore  # noqa: F401
except ModuleNotFoundError:
    if "watchdog.observers" not in sys.modules:
        watchdog_observers = ModuleType("watchdog.observers")
        watchdog_observers.Observer = _Observer
        sys.modules["watchdog.observers"] = watchdog_observers
        _watchdog_module.observers = watchdog_observers


class _CollectorRegistry:
    pass


class _Gauge:
    def __init__(self, *args, **kwargs):
        pass

    def labels(self, *args, **kwargs):
        return self

    def set(self, *args, **kwargs):
        return None


def _generate_latest(*args, **kwargs) -> bytes:
    return b""


try:  # pragma: no cover
    import prometheus_client  # type: ignore  # noqa: F401
except ModuleNotFoundError:
    if "prometheus_client" not in sys.modules:
        prom_module = ModuleType("prometheus_client")
        prom_module.CollectorRegistry = _CollectorRegistry
        prom_module.Gauge = _Gauge
        prom_module.CONTENT_TYPE_LATEST = "text/plain"
        prom_module.generate_latest = _generate_latest
        sys.modules["prometheus_client"] = prom_module

from backend.app.api import domains as domains_api  # noqa: E402
from backend.app.db import AppStateDB  # noqa: E402


def _seed_documents(state_db) -> None:
    job_id = "job-1"
    state_db.record_crawl_job(
        job_id, query="test", normalized_path="/tmp/normalized.jsonl"
    )
    state_db.update_crawl_status(job_id, "success")
    state_db.upsert_document(
        job_id=job_id,
        document_id="doc-1",
        url="https://example.com/page",
        canonical_url="https://example.com/page",
        site="example.com",
        title="Example Page",
        description="Sample doc",
        language="en",
        fetched_at=0.0,
        normalized_path="/tmp/normalized.jsonl",
        text_len=120,
        tokens=24,
        content_hash="hash-1",
        categories=["misc"],
        labels=["demo"],
        source="test",
        verification={"hash": "hash-1"},
    )
    state_db.upsert_document(
        job_id=job_id,
        document_id="doc-2",
        url="https://blog.example.com/post",
        canonical_url="https://blog.example.com/post",
        site="blog.example.com",
        title="Blog Post",
        description="Subdomain doc",
        language="en",
        fetched_at=0.0,
        normalized_path="/tmp/normalized.jsonl",
        text_len=200,
        tokens=48,
        content_hash="hash-2",
        categories=["misc"],
        labels=["demo"],
        source="test",
        verification={"hash": "hash-2"},
    )


def _make_app(db_path: str | Path):
    app = Flask(__name__)
    state_db = AppStateDB(Path(db_path))
    app.config["APP_STATE_DB"] = state_db
    app.register_blueprint(domains_api.bp)
    return app, state_db


def test_domain_scan_and_fetch(monkeypatch: pytest.MonkeyPatch, tmp_path):
    db_path = tmp_path / f"state-{uuid.uuid4().hex}.sqlite3"
    app, state_db = _make_app(str(db_path))
    client = app.test_client()
    _seed_documents(state_db)

    sample_robots = (
        "User-agent: *\n"
        "Disallow: /account\n"
        "Sitemap: https://example.com/sitemap.xml\n"
        "Sitemap: https://example.com/news.xml\n"
    )
    monkeypatch.setattr(
        "backend.app.services.domain_profiles._download_robots",
        lambda host: sample_robots,
    )

    initial = client.get("/api/domains/example.com")
    assert initial.status_code == 200
    assert initial.get_json()["pages_cached"] == 0

    response = client.post("/api/domains/scan", query_string={"host": "example.com"})
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["pages_cached"] == 1
    assert payload["robots_disallows"] == 1
    assert payload["sitemaps"] == [
        "https://example.com/sitemap.xml",
        "https://example.com/news.xml",
    ]
    assert payload["subdomains"] == ["blog.example.com"]
    assert payload["clearance"] == "limited"
    assert payload["requires_account"] is True

    repeat = client.get("/api/domains/example.com")
    assert repeat.status_code == 200
    refreshed = repeat.get_json()
    assert refreshed["pages_cached"] == 1
    assert refreshed["subdomains"] == ["blog.example.com"]


def test_domain_scan_requires_host(monkeypatch: pytest.MonkeyPatch, tmp_path):
    db_path = tmp_path / f"state-{uuid.uuid4().hex}.sqlite3"
    app, _state_db = _make_app(str(db_path))
    client = app.test_client()
    response = client.post("/api/domains/scan")
    assert response.status_code == 400
    data = response.get_json()
    assert data["error"] == "host is required"
