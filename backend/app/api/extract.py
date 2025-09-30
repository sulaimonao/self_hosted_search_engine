"""Server-side page extraction using Playwright and Trafilatura."""

from __future__ import annotations

import base64
import json
from contextlib import suppress
from typing import Any

from flask import Blueprint, g, jsonify, request
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright
import trafilatura

from server.json_logger import log_event

bp = Blueprint("extract_api", __name__, url_prefix="/api")

_DEFAULT_TIMEOUT_MS = 30_000


def _should_capture_vision() -> bool:
    flag = request.args.get("vision", "").strip().lower()
    return flag in {"1", "true", "yes", "on"}


def _extract_text(html: str) -> tuple[str, dict[str, Any]]:
    metadata: dict[str, Any] = {}
    with suppress(Exception):
        meta_json = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=False,
            include_images=False,
            output_format="json",
        )
        if meta_json:
            data = json.loads(meta_json)
            text = data.get("text") or ""
            if isinstance(text, str):
                metadata = {
                    key: value
                    for key, value in data.items()
                    if key in {"title", "lang", "description"}
                }
                return text, metadata
    text = trafilatura.extract(
        html,
        include_comments=False,
        include_tables=False,
        include_images=False,
    )
    if isinstance(text, str):
        return text, metadata
    return "", metadata


def _playwright_extract(url: str, capture_vision: bool) -> dict[str, Any]:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(ignore_https_errors=True)
        page = context.new_page()
        page.set_default_navigation_timeout(_DEFAULT_TIMEOUT_MS)
        page.set_default_timeout(_DEFAULT_TIMEOUT_MS)

        try:
            page.goto(url, wait_until="domcontentloaded")
            html = page.content()
            page_title = page.title()
            lang = page.evaluate("document.documentElement?.lang || null")
            text, meta = _extract_text(html)
            if not text.strip():
                fallback_text = page.evaluate(
                    "document.body ? document.body.innerText : ''"
                )
                if isinstance(fallback_text, str):
                    text = fallback_text
            screenshot_b64: str | None = None
            if capture_vision:
                with suppress(Exception):
                    image = page.screenshot(full_page=True, type="png")
                    if isinstance(image, (bytes, bytearray)):
                        screenshot_b64 = base64.b64encode(image).decode("ascii")
        finally:
            with suppress(Exception):
                context.close()
            with suppress(Exception):
                browser.close()

    payload = {
        "url": url,
        "title": page_title,
        "text": text,
    }
    if lang:
        payload["lang"] = lang
    if meta:
        payload.setdefault("metadata", meta)
    if screenshot_b64:
        payload["screenshot_b64"] = screenshot_b64
    return payload


@bp.post("/extract")
def extract() -> Any:
    payload = request.get_json(silent=True) or {}
    url = (payload.get("url") or "").strip()
    if not url:
        return jsonify({"error": "url_required"}), 400

    trace_id = getattr(g, "trace_id", None)
    capture_vision = _should_capture_vision()

    log_event(
        "INFO",
        "extract.start",
        trace=trace_id,
        url=url,
        vision=capture_vision,
    )

    try:
        result = _playwright_extract(url, capture_vision)
    except PlaywrightTimeout as exc:
        log_event(
            "ERROR",
            "extract.timeout",
            trace=trace_id,
            url=url,
            msg=str(exc),
        )
        return jsonify({"error": "timeout", "message": str(exc)}), 504
    except PlaywrightError as exc:
        log_event(
            "ERROR",
            "extract.playwright_error",
            trace=trace_id,
            url=url,
            error=exc.__class__.__name__,
            msg=str(exc),
        )
        return jsonify({"error": "extract_failed", "message": str(exc)}), 502
    except Exception as exc:  # pragma: no cover - defensive fallback
        log_event(
            "ERROR",
            "extract.error",
            trace=trace_id,
            url=url,
            error=exc.__class__.__name__,
            msg=str(exc),
        )
        return jsonify({"error": "extract_failed", "message": str(exc)}), 502

    log_event(
        "INFO",
        "extract.done",
        trace=trace_id,
        url=url,
        chars=len(result.get("text", "")),
        has_img=bool(result.get("screenshot_b64")),
    )
    return jsonify(result)


__all__ = ["bp"]
