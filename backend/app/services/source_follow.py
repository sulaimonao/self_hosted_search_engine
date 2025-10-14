"""Source discovery helpers for following citations during crawls."""

from __future__ import annotations

import dataclasses
import json
import re
from dataclasses import dataclass
from typing import List, Mapping, MutableMapping, Sequence
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
ARXIV_RE = re.compile(r"arxiv\.org/(abs|pdf)/[0-9]{4}\.[0-9]{4,5}(v\d+)?", re.IGNORECASE)
ISBN_RE = re.compile(r"(97(8|9))?\d{9}(\d|X)", re.IGNORECASE)


@dataclass(slots=True)
class SourceLink:
    url: str
    kind: str


@dataclass(slots=True)
class SourceFollowConfig:
    enabled: bool = False
    max_depth: int = 1
    max_sources_per_page: int = 20
    max_total_sources: int = 200
    allowed_domains: Sequence[str] = dataclasses.field(default_factory=list)
    file_types: Sequence[str] = dataclasses.field(default_factory=lambda: ["html", "pdf"])
    max_bytes_per_source: int = 200 * 1024 * 1024
    session_id: str | None = None

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object] | None) -> "SourceFollowConfig":
        if not payload:
            return cls()
        enabled = bool(payload.get("enabled", False))
        max_depth = max(0, int(payload.get("max_depth", 1)))
        max_sources_per_page = max(1, int(payload.get("max_sources_per_page", 20)))
        max_total_sources = max(1, int(payload.get("max_total_sources", 200)))
        allowed_domains_raw = payload.get("allowed_domains", [])
        allowed_domains: list[str]
        if isinstance(allowed_domains_raw, str):
            allowed_domains = [allowed_domains_raw]
        elif isinstance(allowed_domains_raw, Sequence):
            allowed_domains = [str(item).strip().lower() for item in allowed_domains_raw if str(item).strip()]
        else:
            allowed_domains = []
        file_types_raw = payload.get("file_types", [])
        if isinstance(file_types_raw, str):
            file_types = [file_types_raw.lower()]
        elif isinstance(file_types_raw, Sequence):
            file_types = [str(item).strip().lower() for item in file_types_raw if str(item).strip()]
        else:
            file_types = ["html", "pdf"]
        max_bytes_per_source = int(payload.get("max_bytes_per_source", 200 * 1024 * 1024))
        session_id = payload.get("session_id")
        return cls(
            enabled=enabled,
            max_depth=max_depth,
            max_sources_per_page=max_sources_per_page,
            max_total_sources=max_total_sources,
            allowed_domains=allowed_domains,
            file_types=file_types,
            max_bytes_per_source=max_bytes_per_source,
            session_id=str(session_id) if isinstance(session_id, str) and session_id.strip() else None,
        )

    def to_json(self) -> str:
        payload = self.to_dict()
        return json.dumps(payload, sort_keys=True)

    def to_dict(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "max_depth": self.max_depth,
            "max_sources_per_page": self.max_sources_per_page,
            "max_total_sources": self.max_total_sources,
            "allowed_domains": list(self.allowed_domains),
            "file_types": list(self.file_types),
            "max_bytes_per_source": int(self.max_bytes_per_source),
            "session_id": self.session_id,
        }


class BudgetExceeded(RuntimeError):
    """Raised when a configured budget prevents further source enqueues."""


class SourceBudget:
    """In-memory governor tracking depth and total limits for a crawl session."""

    def __init__(self, config: SourceFollowConfig) -> None:
        self.config = config
        self.total_followed = 0
        self.parent_depths: MutableMapping[str, int] = {}

    def note_parent(self, url: str, depth: int) -> None:
        self.parent_depths[url] = max(0, depth)

    def can_follow(self, parent_url: str, candidate_url: str, *, kind: str, depth: int) -> bool:
        if not self.config.enabled:
            return False
        if depth > self.config.max_depth:
            return False
        if self.total_followed >= self.config.max_total_sources:
            raise BudgetExceeded("maximum total sources reached")
        domain = urlparse(candidate_url).netloc.lower()
        if self.config.allowed_domains:
            normalized = domain[4:] if domain.startswith("www.") else domain
            allowed = {d.lstrip("www.") for d in self.config.allowed_domains}
            if normalized not in allowed:
                return False
        allowed_types = {token.lower() for token in self.config.file_types}
        if allowed_types:
            if kind.lower() in allowed_types:
                return True
            parsed = urlparse(candidate_url)
            path = (parsed.path or "").lower()
            extension = path.rsplit(".", 1)[-1] if "." in path else ""
            if extension and extension in allowed_types:
                return True
            if "html" in allowed_types and (not extension or extension in {"html", "htm"}):
                return True
            return False
        return True

    def record_follow(self) -> None:
        self.total_followed += 1


def classify_source(href: str, text: str | None = None, *, content_type_hint: str | None = None) -> str:
    lowered = href.lower()
    if lowered.endswith(".pdf") or (content_type_hint and "pdf" in content_type_hint.lower()):
        return "pdf"
    if DOI_RE.search(href) or (text and DOI_RE.search(text)):
        return "doi"
    if ARXIV_RE.search(href):
        return "arxiv"
    if text and "isbn" in text.lower():
        return "isbn"
    if text and ISBN_RE.search(text):
        return "isbn"
    if any(token in lowered for token in ["figshare", "zenodo", "huggingface.co/datasets", "data.gov"]):
        return "dataset"
    return "html"


def extract_sources(html: str, base_url: str, *, content_type_hint: str | None = None) -> List[SourceLink]:
    soup = BeautifulSoup(html, "lxml")
    links: list[SourceLink] = []
    seen: set[str] = set()
    for anchor in soup.select("a[href]"):
        href = anchor.get("href")
        if not href:
            continue
        resolved = urljoin(base_url, href)
        text = anchor.get_text(strip=True)
        kind = classify_source(resolved, text, content_type_hint=content_type_hint)
        parent = anchor.find_parent()
        parent_id = parent.get("id", "") if parent is not None else ""
        rel_values = anchor.get("rel") or []
        if rel_values and any("citation" in value.lower() for value in rel_values):
            pass
        elif parent_id and re.search(r"ref|citation|source", parent_id, re.IGNORECASE):
            pass
        elif kind in {"pdf", "doi", "arxiv", "isbn", "dataset"}:
            pass
        else:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        links.append(SourceLink(url=resolved, kind=kind))
        if len(links) >= 200:
            break
    return links


def normalize_config(raw: Mapping[str, object] | None) -> SourceFollowConfig:
    return SourceFollowConfig.from_mapping(raw)


def serialize_config(config: SourceFollowConfig) -> str:
    return config.to_json()
