from __future__ import annotations

import base64
from typing import Any

import pytest

from backend.app.api import extract as extract_mod


class _DummyPage:
    def __init__(self, *, screenshot_bytes: bytes, fallback_text: str) -> None:
        self._screenshot_bytes = screenshot_bytes
        self._fallback_text = fallback_text
        self.closed = False
        self.goto_url: str | None = None

    def set_default_navigation_timeout(
        self, _timeout: int
    ) -> None:  # pragma: no cover - no-op
        return None

    def set_default_timeout(self, _timeout: int) -> None:  # pragma: no cover - no-op
        return None

    def goto(self, url: str, *, wait_until: str) -> None:
        self.goto_url = url
        assert wait_until == "domcontentloaded"

    @staticmethod
    def content() -> str:
        return "<html><body>content</body></html>"

    @staticmethod
    def title() -> str:
        return "Example Page"

    @staticmethod
    def evaluate(script: str) -> Any:
        if "document.documentElement" in script:
            return "en"
        if "document.body" in script:
            return "fallback text"
        return None

    def screenshot(self, *, full_page: bool, type: str) -> bytes:
        assert full_page is True
        assert type == "png"
        return self._screenshot_bytes

    def close(self) -> None:  # pragma: no cover - defensive
        self.closed = True


class _DummyContext:
    def __init__(self, page: _DummyPage) -> None:
        self._page = page
        self.closed = False

    def new_page(self) -> _DummyPage:
        return self._page

    def close(self) -> None:
        self.closed = True


class _DummyBrowser:
    def __init__(self, context: _DummyContext) -> None:
        self._context = context
        self.closed = False

    def new_context(self, *, ignore_https_errors: bool) -> _DummyContext:
        assert ignore_https_errors is True
        return self._context

    def close(self) -> None:
        self.closed = True


class _DummyChromium:
    def __init__(self, browser: _DummyBrowser) -> None:
        self._browser = browser

    def launch(self, *, headless: bool) -> _DummyBrowser:
        assert headless is True
        return self._browser


class _DummyPlaywrightManager:
    def __init__(self, playwright: Any) -> None:
        self._playwright = playwright

    def __enter__(self) -> Any:
        return self._playwright

    def __exit__(self, *_exc: object) -> None:
        return None


def test_playwright_extract_returns_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    screenshot = b"image-bytes"
    dummy_page = _DummyPage(screenshot_bytes=screenshot, fallback_text="fallback text")
    dummy_context = _DummyContext(page=dummy_page)
    dummy_browser = _DummyBrowser(context=dummy_context)
    dummy_chromium = _DummyChromium(browser=dummy_browser)

    class _DummyPlaywright:
        chromium = dummy_chromium

    monkeypatch.setattr(
        extract_mod,
        "sync_playwright",
        lambda: _DummyPlaywrightManager(_DummyPlaywright()),
    )
    monkeypatch.setattr(
        extract_mod,
        "_extract_text",
        lambda _html: ("", {}),
    )

    payload = extract_mod._playwright_extract(
        "https://example.com", capture_vision=True
    )

    assert payload["url"] == "https://example.com"
    assert payload["title"] == "Example Page"
    assert payload["text"] == "fallback text"
    assert payload["lang"] == "en"
    expected_b64 = base64.b64encode(screenshot).decode("ascii")
    assert payload["screenshot_b64"] == expected_b64
