"""Source loaders for cold-start crawl seeds."""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Sequence
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree

LOGGER = logging.getLogger(__name__)

DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
SEEDS_DIR = DATA_DIR / "seeds"
COMMONCRAWL_DIR = DATA_DIR / "commoncrawl"
SITEMAPS_DIR = SEEDS_DIR / "sitemaps"

_URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)
_DOMAIN_RE = re.compile(r"^(?:https?://)?([a-z0-9.-]+)\/?", re.IGNORECASE)


@dataclass(slots=True)
class SeedSource:
    """Normalized representation of a seed URL discovered from disk."""

    url: str
    source: str
    tags: set[str] = field(default_factory=set)
    metadata: Dict[str, str] = field(default_factory=dict)


def _sanitize_url(value: str) -> str | None:
    candidate = (value or "").strip()
    if not candidate:
        return None
    match = _URL_RE.search(candidate)
    if match:
        candidate = match.group(0)
    elif _DOMAIN_RE.match(candidate):
        candidate = f"https://{candidate.lstrip('/')}"
    else:
        return None
    parsed = urlparse(candidate)
    if not parsed.scheme or not parsed.netloc:
        return None
    sanitized = f"{parsed.scheme}://{parsed.netloc}{parsed.path or ''}".rstrip("/")
    return sanitized or None


def _iter_lines(paths: Iterable[Path]) -> Iterator[tuple[str, Path]]:
    for path in paths:
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    text = line.strip()
                    if not text or text.startswith("#"):
                        continue
                    yield text, path
        except FileNotFoundError:
            continue
        except OSError as exc:  # pragma: no cover - filesystem errors are rare
            LOGGER.debug("failed to read %s: %s", path, exc)


def load_domain_sources(base_dir: Path | None = None) -> List[SeedSource]:
    """Load curated domain/TLD lists from ``data/seeds``."""

    seeds_dir = base_dir or SEEDS_DIR
    patterns = sorted(seeds_dir.glob("*.txt"))
    results: List[SeedSource] = []
    for raw, path in _iter_lines(patterns):
        url = _sanitize_url(raw)
        if not url:
            continue
        tags = {"list"}
        stem = path.stem.lower()
        if "nonus" in stem or "intl" in stem:
            tags.add("non_us_hint")
        if "nonen" in stem or "intl" in stem:
            tags.add("non_en_hint")
        results.append(SeedSource(url=url, source=f"list:{path.name}", tags=tags))
    return results


def load_commoncrawl_sources(base_dir: Path | None = None) -> List[SeedSource]:
    """Load CommonCrawl URL dumps if available locally."""

    cc_dir = base_dir or COMMONCRAWL_DIR
    paths = sorted(cc_dir.glob("*.txt"))
    results: List[SeedSource] = []
    for raw, path in _iter_lines(paths):
        url = _sanitize_url(raw)
        if not url:
            continue
        results.append(
            SeedSource(
                url=url,
                source=f"commoncrawl:{path.name}",
                tags={"commoncrawl"},
            )
        )
    return results


def _parse_sitemap(path: Path) -> Iterator[str]:
    try:
        tree = ElementTree.parse(path)
    except ElementTree.ParseError:
        LOGGER.debug("invalid sitemap XML at %s", path)
        return iter(())
    root = tree.getroot()
    for element in root.iter():
        if not element.tag.lower().endswith("loc"):
            continue
        if not element.text:
            continue
        url = _sanitize_url(element.text)
        if url:
            yield url


def load_sitemap_sources(
    curated_hosts: Sequence[str] | None = None,
    *,
    sitemaps_dir: Path | None = None,
) -> List[SeedSource]:
    """Load URLs from sitemap snapshots under ``data/seeds/sitemaps``.

    When ``curated_hosts`` is provided, only sitemap files whose parent directory
    name matches one of the hosts will be parsed.
    """

    base_dir = sitemaps_dir or SITEMAPS_DIR
    if not base_dir.exists():
        return []

    if curated_hosts:
        normalized = {host.strip().lower() for host in curated_hosts if host.strip()}
        candidates = [
            path
            for host in normalized
            for path in (base_dir / host).glob("**/*.xml")
        ]
    else:
        candidates = list(base_dir.glob("**/*.xml"))

    results: List[SeedSource] = []
    for path in sorted(candidates):
        for url in _parse_sitemap(path):
            results.append(
                SeedSource(
                    url=url,
                    source=f"sitemap:{path.relative_to(base_dir)}",
                    tags={"sitemap"},
                )
            )
    # Allow JSON snapshots as a fallback for developers who already pre-processed
    # sitemap URLs into plain arrays.
    json_candidates = list(base_dir.glob("**/*.json"))
    for path in sorted(json_candidates):
        try:
            payload = json.loads(path.read_text("utf-8"))
        except (ValueError, OSError):
            continue
        if isinstance(payload, dict):
            payload = payload.get("urls")
        if not isinstance(payload, list):
            continue
        for entry in payload:
            url = _sanitize_url(str(entry))
            if url:
                results.append(
                    SeedSource(
                        url=url,
                        source=f"sitemap:{path.relative_to(base_dir)}",
                        tags={"sitemap", "json"},
                    )
                )
    return results


def discover_sources(curated_hosts: Sequence[str] | None = None) -> List[SeedSource]:
    """Convenience helper that loads every supported seed source."""

    seeds: List[SeedSource] = []
    seeds.extend(load_domain_sources())
    seeds.extend(load_commoncrawl_sources())
    seeds.extend(load_sitemap_sources(curated_hosts))
    LOGGER.info("loaded %d raw seed candidates from disk", len(seeds))
    return seeds


__all__ = [
    "SeedSource",
    "discover_sources",
    "load_commoncrawl_sources",
    "load_domain_sources",
    "load_sitemap_sources",
]
