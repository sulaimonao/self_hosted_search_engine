"""Detection helpers for authentication and paywall requirements."""

from __future__ import annotations

import re
import time
from urllib.parse import urlparse
from typing import Any

from ..db import domain_profiles


PAYWALL_PATTERNS = {
    "piano": r"tinypass|tp\.flexible|piano-io",
    "arc": r"arcwp|arc-pub|arc-adsystem",
    "zephr": r"zephr|cdn\.zephr",
    "laterpay": r"laterpay",
}

LOGIN_REDIRECT_HINTS = ("/login", "/signin", "/account", "auth", "authorize")
ANTI_BOT_HINTS = ("cf-chl-", "__cf_bm", "captcha", "challenge-platform")


def detect_clearance(
    response, html: str | None, url: str | None = None
) -> dict[str, Any]:
    info = {
        "requires_login": False,
        "paywall_vendor": None,
        "paywall_pattern": None,
        "anti_bot": False,
        "signals": [],
    }

    if response is None:
        return info

    location = (
        response.headers.get("Location", "") if hasattr(response, "headers") else ""
    )
    status = getattr(response, "status_code", 0) or 0
    html_text = html or ""

    if 300 <= status < 400 and location:
        lowered = location.lower()
        if any(token in lowered for token in LOGIN_REDIRECT_HINTS):
            info["requires_login"] = True
            info["signals"].append(f"redirect:{location}")

    lowered_html = html_text.lower()
    for vendor, pattern in PAYWALL_PATTERNS.items():
        if re.search(pattern, lowered_html):
            info["paywall_vendor"] = vendor
            info["paywall_pattern"] = pattern
            info["requires_login"] = True
            info["signals"].append(f"paywall:{vendor}")
            break

    if any(hint in lowered_html for hint in ANTI_BOT_HINTS):
        info["anti_bot"] = True
        info["signals"].append("anti_bot")

    domain = _extract_domain(url or getattr(response, "url", ""))
    if domain:
        domain_profiles.upsert(
            {
                "domain": domain,
                "requires_login": info["requires_login"],
                "paywall_vendor": info["paywall_vendor"],
                "paywall_pattern": info["paywall_pattern"],
                "anti_bot": info["anti_bot"],
                "last_seen": time.time(),
            }
        )

    return info


def _extract_domain(url: str) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    host = parsed.netloc or parsed.path
    host = host.lower()
    if host.startswith("www."):
        host = host[4:]
    return host or None


__all__ = ["detect_clearance"]
