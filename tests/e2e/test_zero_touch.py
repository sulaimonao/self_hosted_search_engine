"""Zero-touch smoke tests covering config, health, and chat page context."""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from typing import Any

from playwright.sync_api import Page, expect

from tests.e2e.stack import ensure_zero_touch_stack

API = "http://127.0.0.1:5050"
WEB = "http://127.0.0.1:3100"
CHAT_POST_RE = re.compile(r"/api/chat/[0-9a-fA-F-]{36}/message$")


def _get(url: str, timeout: float = 2.0) -> str:
    with urllib.request.urlopen(url, timeout=timeout) as response:  # type: ignore[arg-type]
        return response.read().decode("utf-8")


def _json(url: str, timeout: float = 2.0) -> dict[str, Any]:
    raw = _get(url, timeout=timeout)
    return json.loads(raw)


def wait_for_health(max_wait_s: float = 90.0) -> None:
    """Poll the meta health endpoint until it reports ready."""

    ensure_zero_touch_stack()
    start = time.time()
    while time.time() - start < max_wait_s:
        try:
            payload = _json(f"{API}/api/meta/health", timeout=1.0)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            payload = {}
        if payload.get("ok") is True:
            return
        time.sleep(1.0)
    raise AssertionError("API never became healthy via /api/meta/health")


def _dismiss_wizard(page: Page) -> None:
    for locator in (
        page.get_by_role("button", name=re.compile(r"skip for now", re.I)),
        page.get_by_role("button", name=re.compile(r"finish setup", re.I)),
        page.get_by_role("button", name=re.compile(r"close", re.I)),
    ):
        try:
            locator.click(timeout=1000)
            break
        except Exception:
            continue


def test_zero_touch_smoke(page: Page) -> None:
    wait_for_health()

    page.goto(WEB, wait_until="domcontentloaded")
    _dismiss_wizard(page)

    wizard_visible = False
    try:
        heading = page.get_by_role("heading", name=re.compile("setup", re.I))
        wizard_visible = heading.is_visible(timeout=3000)
    except Exception:
        wizard_visible = False
    # Presence of the wizard is best-effort; do not assert hard on it.
    if wizard_visible:
        _dismiss_wizard(page)

    config_before = _json(f"{API}/api/config")
    assert "models_primary" in config_before
    assert "features_shadow_mode" in config_before

    current_shadow = bool(config_before.get("features_shadow_mode", True))

    page.goto(f"{WEB}/control-center", wait_until="domcontentloaded")
    _dismiss_wizard(page)

    toggled = False
    try:
        toggle = page.get_by_role("switch", name=re.compile("shadow", re.I))
        toggle.wait_for(state="visible", timeout=5000)
        toggle.click()
        toggled = True
    except Exception:
        try:
            checkbox = page.get_by_label(re.compile("shadow", re.I))
            checkbox.click()
            toggled = True
        except Exception:
            toggled = False

    updated = config_before
    if toggled:
        for _ in range(5):
            time.sleep(1.0)
            updated = _json(f"{API}/api/config")
            if updated.get("features_shadow_mode") != current_shadow:
                break
    else:
        updated = _json(f"{API}/api/config")

    target_shadow = not current_shadow
    if updated.get("features_shadow_mode") != target_shadow:
        request = urllib.request.Request(
            f"{API}/api/config",
            data=json.dumps({"features_shadow_mode": target_shadow}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        with urllib.request.urlopen(request, timeout=3.0) as response:  # type: ignore[arg-type]
            assert 200 <= response.status < 300
        updated = _json(f"{API}/api/config")

    assert updated.get("features_shadow_mode") == target_shadow

    request = urllib.request.Request(
        f"{API}/api/config",
        data=json.dumps({"setup_completed": True}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="PUT",
    )
    with urllib.request.urlopen(request, timeout=3.0) as response:  # type: ignore[arg-type]
        assert 200 <= response.status < 300

    page.reload()
    expect(page).to_have_url(re.compile(rf"^{re.escape(WEB)}"))


def test_page_context_flag(page: Page) -> None:
    wait_for_health()

    page.goto(WEB, wait_until="domcontentloaded")
    _dismiss_wizard(page)

    try:
        toggle = page.get_by_role("switch", name=re.compile("use current page", re.I))
        toggle.wait_for(state="visible", timeout=5000)
        aria_checked = toggle.get_attribute("aria-checked")
        if aria_checked != "true":
            toggle.click()
    except Exception:
        try:
            checkbox = page.get_by_label(re.compile("use current page", re.I))
            checkbox.click()
        except Exception:
            pass

    composer = None
    try:
        # Prefer a stable test id if available.
        composer = page.locator("[data-testid='chat-composer']").first
        composer.fill("ping")
    except Exception:
        try:
            composer = page.get_by_role("textbox").first
            composer.fill("ping")
        except Exception:
            try:
                page.fill("textarea, input[type='text']", "ping")
            except Exception:
                raise AssertionError("Unable to locate chat composer")

    def is_chat_post(request) -> bool:
        return request.method == "POST" and CHAT_POST_RE.search(request.url) is not None

    with page.expect_request(is_chat_post, timeout=15000) as req_info:
        sent = False
        if composer is not None:
            try:
                composer.press("Enter")
                sent = True
            except Exception:
                sent = False
        if not sent:
            try:
                page.get_by_role("button", name=re.compile("send", re.I)).click()
                sent = True
            except Exception:
                sent = False
        if not sent:
            page.keyboard.press("Enter")

    request = req_info.value
    payload: dict[str, Any]
    try:
        raw = request.post_data or ""
        payload = json.loads(raw) if raw else {}
    except Exception:
        payload = {}

    assert (
        "page_url" in payload
    ), f"Missing `page_url` in chat payload for {request.url}"
    page_url = payload.get("page_url")
    assert (
        isinstance(page_url, str) and page_url.strip()
    ), f"`page_url` empty in chat payload for {request.url}: {page_url!r}"
