from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import MethodType
from urllib.parse import urlparse

import pytest

from backend.app import create_app
from backend.app.config import AppConfig
from backend.app.indexer.incremental import incremental_index
from backend.app.jobs.focused_crawl import FocusedCrawlSupervisor
from backend.app.pipeline.normalize import normalize


class _TestHandler(BaseHTTPRequestHandler):
    pages: dict[str, str] = {}

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        content = self.pages.get(parsed.path, "<html><body>not found</body></html>")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(content.encode("utf-8"))

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


@pytest.fixture()
def http_server():
    handler = _TestHandler
    handler.pages = {
        "/": """
            <html><head><title>Welcome</title></head>
            <body>
              <h1>Welcome to the docs</h1>
              <a href="/docs/getting-started.html">Getting started</a>
            </body>
            </html>
        """,
        "/docs/getting-started.html": """
            <html><head><title>Getting Started</title></head>
            <body>
              <h1>Python packaging guide</h1>
              <p>Install packages with pip and build wheels.</p>
            </body>
            </html>
        """,
        "/docs/advanced.html": """
            <html><head><title>Advanced Packaging</title></head>
            <body>
              <h1>Advanced topics</h1>
              <p>Learn how to manage dependencies and lock files.</p>
            </body>
            </html>
        """,
    }
    server = HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=1)


@pytest.mark.integration()
def test_cold_start_focus(monkeypatch, tmp_path, http_server):
    data_dir = tmp_path / "data"
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("FOCUSED_CRAWL_ENABLED", "1")
    monkeypatch.setenv("SMART_TRIGGER_COOLDOWN", "0")
    monkeypatch.setenv("FOCUSED_CRAWL_BUDGET", "5")
    monkeypatch.setenv("CRAWL_USE_PLAYWRIGHT", "0")
    monkeypatch.setenv("CRAWL_RESPECT_ROBOTS", "0")

    base_url = http_server

    app = create_app()
    app.testing = True
    supervisor: FocusedCrawlSupervisor = app.config["FOCUSED_SUPERVISOR"]

    def immediate_schedule(self: FocusedCrawlSupervisor, query: str, use_llm: bool, model: str | None) -> bool:
        self.config.crawl_raw_dir.mkdir(parents=True, exist_ok=True)
        raw_file = self.config.crawl_raw_dir / "test.jsonl"
        with raw_file.open("w", encoding="utf-8") as handle:
            for path, html in _TestHandler.pages.items():
                handle.write(
                    json.dumps(
                        {
                            "url": f"{base_url}{path}",
                            "status": 200,
                            "html": html,
                            "title": "Fixture",
                        }
                    )
                    + "\n"
                )
        docs = normalize(self.config.crawl_raw_dir, self.config.normalized_path)
        incremental_index(
            self.config.index_dir,
            self.config.ledger_path,
            self.config.simhash_path,
            self.config.last_index_time_path,
            docs,
        )
        self._history[query] = 0.0
        return True

    supervisor.schedule = MethodType(immediate_schedule, supervisor)

    client = app.test_client()
    response = client.get("/api/search", query_string={"q": "python packaging guides"})
    payload = response.get_json()
    assert payload["status"] == "focused_crawl_running"
    assert payload["results"] == []

    payload = {}
    for _ in range(5):
        response = client.get("/api/search", query_string={"q": "python packaging guides"})
        payload = response.get_json()
        if payload.get("results"):
            break
    assert payload.get("results"), "Expected results after focused crawl finished"
    urls = [item["url"] for item in payload["results"]]
    assert any(url.startswith(base_url) for url in urls)

    config = AppConfig.from_env()
    assert (config.index_dir).exists()
    assert (config.last_index_time_path).exists()
