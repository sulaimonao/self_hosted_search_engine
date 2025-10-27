"""Domain profile scanning and persistence helpers."""

from __future__ import annotations

import time
import urllib.parse
from typing import Any, Sequence

import httpx
from flask import current_app

from backend.app.db import AppStateDB

MAX_ROBOTS_BYTES = 64 * 1024
ROBOTS_TIMEOUT = 8.0
USER_AGENT = "SelfHostedSearchBot/0.1"

_PAYWALL_HINTS = (
    "disallow: /paywall",
    "disallow: /subscribe",
    "disallow: /premium",
    "disallow: /billing",
)
_AUTH_HINTS = (
    "disallow: /login",
    "disallow: /signin",
    "disallow: /auth",
    "disallow: /account/login",
)
_LIMITED_HINTS = (
    "disallow: /account",
    "disallow: /user",
    "disallow: /profile",
    "disallow: /settings",
)


def _state_db() -> AppStateDB:
    state_db = current_app.config.get("APP_STATE_DB")
    if state_db is None:  # pragma: no cover - configured in app factory
        raise RuntimeError("APP_STATE_DB is not configured")
    return state_db


def _normalize_host(host: str) -> str:
    text = (host or "").strip()
    if not text:
        raise ValueError("host is required")
    candidate = text
    if "://" not in candidate:
        candidate = f"https://{candidate}"
    parsed = urllib.parse.urlparse(candidate)
    netloc = parsed.netloc or parsed.path
    if not netloc:
        raise ValueError("host is required")
    if "@" in netloc:
        netloc = netloc.split("@", 1)[1]
    hostname = netloc.split(":", 1)[0].strip().lower()
    if hostname.startswith("www."):
        hostname = hostname[4:]
    hostname = hostname.strip(".")
    if not hostname:
        raise ValueError("host is required")
    try:
        hostname = hostname.encode("idna").decode("ascii")
    except UnicodeError:
        pass
    return hostname


def _download_robots(host: str) -> str:
    headers = {"User-Agent": USER_AGENT}
    for scheme in ("https", "http"):
        url = f"{scheme}://{host}/robots.txt"
        try:
            response = httpx.get(
                url,
                headers=headers,
                timeout=ROBOTS_TIMEOUT,
                follow_redirects=True,
            )
        except httpx.HTTPError:
            current_app.logger.debug("robots fetch failed for %s", url, exc_info=True)
            continue
        if response.status_code >= 400:
            continue
        text = response.text or ""
        if len(text) > MAX_ROBOTS_BYTES:
            text = text[:MAX_ROBOTS_BYTES]
        return text
    return ""


def _count_directives(robots_txt: str) -> tuple[int, int]:
    allows = 0
    disallows = 0
    for raw_line in (robots_txt or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        lowered = line.lower()
        if lowered.startswith("allow:"):
            allows += 1
        elif lowered.startswith("disallow:"):
            disallows += 1
    return allows, disallows


def extract_sitemaps(robots_txt: str) -> list[str]:
    sitemaps: list[str] = []
    seen: set[str] = set()
    for raw_line in (robots_txt or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("sitemap:"):
            url = line.split(":", 1)[1].strip()
            if not url:
                continue
            if url in seen:
                continue
            seen.add(url)
            sitemaps.append(url)
    return sitemaps


def _infer_clearance(robots_txt: str) -> tuple[str, bool]:
    lowered = (robots_txt or "").lower()
    requires_account = False
    clearance = "public"
    if any(token in lowered for token in _PAYWALL_HINTS):
        clearance = "paywalled"
        requires_account = True
    elif any(token in lowered for token in _AUTH_HINTS):
        clearance = "auth"
        requires_account = True
    elif any(token in lowered for token in _LIMITED_HINTS):
        clearance = "limited"
        requires_account = True
    return clearance, requires_account


def _dedupe(values: Sequence[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if not text:
            continue
        lowered = text.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        cleaned.append(text)
    return cleaned


def count_docs_for_host(host: str) -> int:
    return _state_db().count_documents_for_site(host)


def guess_subdomains_from_index(host: str, *, limit: int = 10) -> list[str]:
    return _state_db().list_known_subdomains(host, limit=limit)


def get_domain(host: str) -> dict[str, Any]:
    normalized = _normalize_host(host)
    record = _state_db().get_domain_profile(normalized)
    if record:
        record["host"] = normalized
        return record
    return {
        "host": normalized,
        "pages_cached": 0,
        "robots_txt": None,
        "robots_allows": 0,
        "robots_disallows": 0,
        "requires_account": False,
        "clearance": "public",
        "sitemaps": [],
        "subdomains": [],
        "last_scanned": None,
    }


def scan_domain(host: str) -> dict[str, Any]:
    normalized = _normalize_host(host)
    pages = count_docs_for_host(normalized)
    robots_txt = _download_robots(normalized)
    allows, disallows = _count_directives(robots_txt)
    sitemaps = extract_sitemaps(robots_txt)
    subdomains = guess_subdomains_from_index(normalized)
    clearance, requires_account = _infer_clearance(robots_txt)
    state_db = _state_db()
    state_db.upsert_domain_profile(
        host=normalized,
        pages_cached=pages,
        robots_txt=robots_txt,
        robots_allows=allows,
        robots_disallows=disallows,
        requires_account=requires_account,
        clearance=clearance,
        sitemaps=_dedupe(sitemaps),
        subdomains=_dedupe(subdomains),
        last_scanned=time.time(),
    )
    return get_domain(normalized)


__all__ = [
    "count_docs_for_host",
    "extract_sitemaps",
    "get_domain",
    "guess_subdomains_from_index",
    "scan_domain",
]
