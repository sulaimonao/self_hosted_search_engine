from __future__ import annotations

import hashlib
import posixpath
from datetime import datetime, timezone
from typing import Iterable
from urllib.parse import urlparse, urlunparse, urljoin, parse_qsl, urlencode

from parsel import Selector


CANONICAL_PRIORITY = ["", "/", "/home", "/index", "/about", "/docs", "/documentation", "/blog", "/contact"]


def normalize_url(url: str) -> str:
    parsed = urlparse(url)
    scheme = parsed.scheme.lower() or "http"
    netloc = parsed.netloc.lower()
    if ":" in netloc:
        host, _, port = netloc.partition(":")
        default_port = (scheme == "http" and port == "80") or (scheme == "https" and port == "443")
        netloc = host if default_port else f"{host}:{port}"
    path = parsed.path or "/"
    if not path.startswith("/"):
        path = f"/{path}"
    normalized_path = posixpath.normpath(path)
    if path.endswith("/") and not normalized_path.endswith("/"):
        normalized_path += "/"
    if normalized_path == ".":
        normalized_path = "/"
    query_items = parse_qsl(parsed.query, keep_blank_values=True)
    query = urlencode(sorted(query_items)) if query_items else ""
    return urlunparse((scheme, netloc, normalized_path, "", query, ""))


def canonical_link_priority(urls: Iterable[str]) -> list[str]:
    scored: list[tuple[int, str]] = []
    for url in urls:
        parsed = urlparse(url)
        path = parsed.path or "/"
        try:
            rank = CANONICAL_PRIORITY.index(path.lower())
        except ValueError:
            rank = len(CANONICAL_PRIORITY)
        scored.append((rank, url))
    scored.sort(key=lambda item: (item[0], item[1]))
    return [url for _, url in scored]


def extract_text(html: str) -> str:
    if not html:
        return ""
    selector = Selector(text=html)
    texts = [t.strip() for t in selector.xpath("//body//text()").getall() if t.strip()]
    return " ".join(texts)


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def url_domain(url: str) -> str:
    return urlparse(url).netloc.lower()


def join_url(base: str, link: str) -> str:
    return normalize_url(urljoin(base, link.split("#")[0]))
