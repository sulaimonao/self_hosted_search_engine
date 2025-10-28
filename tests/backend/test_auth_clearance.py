from __future__ import annotations

import pytest

from backend.app.services import auth_clearance
from backend.app.db import domain_profiles


class DummyResponse:
    def __init__(self, url: str, status_code: int = 200, headers: dict[str, str] | None = None) -> None:
        self.url = url
        self.status_code = status_code
        self.headers = headers or {}


@pytest.fixture(autouse=True)
def configure_domain_profiles(tmp_path):
    domain_profiles.configure(tmp_path / "profiles.sqlite3")


def test_detects_paywall_and_records_profile():
    html = "<html><script src='https://cdn.tinypass.com/piano.js'></script></html>"
    response = DummyResponse("https://paywalled.example/article")
    info = auth_clearance.detect_clearance(response, html)
    assert info["paywall_vendor"] == "piano"
    record = domain_profiles.get("paywalled.example")
    assert record is not None
    assert record["requires_login"] is True


def test_detects_login_redirect():
    response = DummyResponse("https://news.example", status_code=302, headers={"Location": "https://news.example/login"})
    info = auth_clearance.detect_clearance(response, "")
    assert info["requires_login"] is True


def test_detects_anti_bot():
    html = "<html><body>cf-chl-bypass</body></html>"
    response = DummyResponse("https://guarded.example")
    info = auth_clearance.detect_clearance(response, html)
    assert info["anti_bot"] is True
