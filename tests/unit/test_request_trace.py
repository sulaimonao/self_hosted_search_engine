from __future__ import annotations

from pathlib import Path

from flask import g, jsonify

from backend.app import create_app


def test_request_trace_header(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    app = create_app()

    @app.get("/trace-check")
    def trace_check():
        return jsonify({"trace": getattr(g, "trace_id", None)})

    client = app.test_client()
    response = client.get("/trace-check")
    payload = response.get_json()
    trace = payload["trace"]

    assert isinstance(trace, str)
    assert trace.startswith("req_")
    assert response.headers["X-Request-Id"] == trace
