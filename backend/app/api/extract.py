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
from bs4 import BeautifulSoup
import trafilatura

from server.json_logger import log_event

bp = Blueprint("extract_api", __name__, url_prefix="/api")

_DEFAULT_TIMEOUT_MS = 30_000


def _should_capture_vision() -> bool:
    flag = request.args.get("vision", "").strip().lower()
    return flag in {"1", "true", "yes", "on"}


def _extract_text(html: str, *, source_url: str | None = None) -> tuple[str, dict[str, Any]]:
    metadata: dict[str, Any] = {}
    with suppress(Exception):
        meta_json = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=False,
            include_images=False,
            output_format="json",
            url=source_url,
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
        url=source_url,
    )
    if isinstance(text, str):
        return text, metadata
    return "", metadata


def _fallback_dom_text(html: str) -> str:
    with suppress(Exception):
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(separator=" ", strip=True)
        if text:
            return text
    return ""


def _dom_title(html: str) -> str | None:
    with suppress(Exception):
        soup = BeautifulSoup(html, "html.parser")
        if soup.title and soup.title.string:
            title = soup.title.string.strip()
            return title or None
    return None


def _dom_extract(source_url: str, html: str, *, title_hint: str | None = None) -> dict[str, Any]:
    text, meta = _extract_text(html, source_url=source_url)
    cleaned_text = text.strip() or _fallback_dom_text(html)
    payload: dict[str, Any] = {
        "url": source_url,
        "text": cleaned_text,
    }
    title = title_hint or meta.get("title") or _dom_title(html)
    if title:
        payload["title"] = title
    lang = meta.get("lang")
    if lang:
        payload["lang"] = lang
    if meta:
        payload.setdefault("metadata", meta)
    return payload


def _playwright_extract(url: str, capture_vision: bool) -> dict[str, Any]:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(ignore_https_errors=True)
        page = context.new_page()
        page.set_default_navigation_timeout(_DEFAULT_TIMEOUT_MS)
        page.set_default_timeout(_DEFAULT_TIMEOUT_MS)

        page_title: str | None = None
        lang: str | None = None
        text: str = ""
        meta: dict[str, Any] = {}
        screenshot_b64: str | None = None

        try:
            page.goto(url, wait_until="domcontentloaded")
            html = page.content()
            page_title = page.title()
            lang = page.evaluate("document.documentElement?.lang || null")
            text, meta = _extract_text(html, source_url=url)
            if not text.strip():
                fallback_text = page.evaluate(
                    "document.body ? document.body.innerText : ''"
                )
                if isinstance(fallback_text, str):
                    text = fallback_text
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

    payload: dict[str, Any] = {
        "url": url,
        "text": text,
    }
    if page_title:
        payload["title"] = page_title
    if lang:
        payload["lang"] = lang
    if meta:
        payload.setdefault("metadata", meta)
    if screenshot_b64:
        payload["screenshot_b64"] = screenshot_b64
    return payload


def _handle_extract(url: str, capture_vision: bool) -> tuple[dict[str, Any], int]:
    trace_id = getattr(g, "trace_id", None)
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
        return {"error": "timeout", "message": str(exc)}, 504
    except PlaywrightError as exc:
        log_event(
            "ERROR",
            "extract.playwright_error",
            trace=trace_id,
            url=url,
            error=exc.__class__.__name__,
            msg=str(exc),
        )
        return {"error": "extract_failed", "message": str(exc)}, 502
    except Exception as exc:  # pragma: no cover - defensive fallback
        log_event(
            "ERROR",
            "extract.error",
            trace=trace_id,
            url=url,
            error=exc.__class__.__name__,
            msg=str(exc),
        )
        return {"error": "extract_failed", "message": str(exc)}, 502

    log_event(
        "INFO",
        "extract.done",
        trace=trace_id,
        url=url,
        chars=len(result.get("text", "")),
        has_img=bool(result.get("screenshot_b64")),
    )
    return result, 200


@bp.post("/extract")
def extract() -> Any:
    payload = request.get_json(silent=True) or {}
    source_url_raw = payload.get("source_url")
    source_url = str(source_url_raw).strip() if isinstance(source_url_raw, str) else ""
    if not source_url:
        return (
            jsonify({"error": "source_url_required", "message": "source_url is required"}),
            400,
        )

    title_hint_raw = payload.get("title")
    title_hint = str(title_hint_raw).strip() if isinstance(title_hint_raw, str) else None
    html_raw = payload.get("html")
    html_value = html_raw if isinstance(html_raw, str) and html_raw.strip() else None

    capture_vision = _should_capture_vision() if not html_value else False
    if html_value:
        try:
            data = _dom_extract(source_url, html_value, title_hint=title_hint)
            return jsonify(data), 200
        except Exception as exc:  # pragma: no cover - defensive guard
            log_event(
                "ERROR",
                "extract.dom_error",
                trace=getattr(g, "trace_id", None),
                url=source_url,
                error=exc.__class__.__name__,
                msg=str(exc),
            )
            return jsonify({"error": "extract_failed", "message": str(exc)}), 502

    data, status = _handle_extract(source_url, capture_vision)
    if title_hint and not data.get("title"):
        data["title"] = title_hint
    return jsonify(data), status


@bp.get("/page/extract")
def extract_page() -> Any:
    raw = request.args.get("source_url") or request.args.get("url") or ""
    url = raw.strip()
    if not url:
        return jsonify({"error": "source_url_required"}), 400

    capture_vision = _should_capture_vision()
    data, status = _handle_extract(url, capture_vision)
    return jsonify(data), status


__all__ = ["bp"]
