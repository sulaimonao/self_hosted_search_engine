"""Ensure the main template exposes diagnostics controls."""

from __future__ import annotations

from app import create_app


def test_index_template_includes_diagnostics_controls() -> None:
    app = create_app()
    client = app.test_client()
    response = client.get("/")
    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert 'id="diagnostics-run"' in html
    assert 'id="diagnostics-panel"' in html
    assert 'id="diagnostics-download"' in html
    assert 'id="diagnostics-log-download"' in html
