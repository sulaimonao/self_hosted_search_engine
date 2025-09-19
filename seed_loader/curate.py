"""Curate diverse high-quality crawl seeds from local sources."""

from __future__ import annotations

import json
import logging
import math
import os
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence
from urllib.parse import urlparse

from .sources import SeedSource, discover_sources

try:  # Optional dependency: local LLM enrichment
    from llm.seed_guesser import guess_urls as llm_guess_urls
except Exception:  # pragma: no cover - best effort fallback
    llm_guess_urls = None

LOGGER = logging.getLogger(__name__)

DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
CURATED_PATH = DATA_DIR / "seeds" / "curated_seeds.jsonl"
NON_EN_QUOTA = float(os.getenv("SEED_QUOTA_NON_EN", "0.30"))
NON_US_QUOTA = float(os.getenv("SEED_QUOTA_NON_US", "0.40"))
CURATED_LIMIT = int(os.getenv("SEED_CURATED_LIMIT", "200"))
SMART_USE_LLM = os.getenv("SMART_USE_LLM", "false").lower() in {"1", "true", "yes", "on"}

_KEYWORDS_DOCS = {"doc", "docs", "documentation", "handbook", "guide", "tutorial"}
_KEYWORDS_COMMUNITY = {"blog", "community", "forum", "kb", "knowledge"}
_REGION_HINTS = {
    "us": {".us", ".gov", ".mil", ".edu"},
    "eu": {".fr", ".de", ".es", ".pt", ".it", ".ie", ".pl", ".nl", ".se", ".no"},
    "latam": {".br", ".mx", ".ar", ".cl", ".pe", ".co"},
    "apac": {".jp", ".cn", ".sg", ".au", ".in", ".kr", ".hk"},
}
_LANG_BY_TLD = {
    "fr": "fr",
    "de": "de",
    "es": "es",
    "pt": "pt",
    "br": "pt",
    "mx": "es",
    "ar": "es",
    "cl": "es",
    "co": "es",
    "jp": "ja",
    "cn": "zh",
    "tw": "zh",
    "hk": "zh",
    "sg": "en",
    "au": "en",
    "in": "en",
    "kr": "ko",
    "ru": "ru",
    "se": "sv",
    "no": "no",
    "fi": "fi",
    "pl": "pl",
    "it": "it",
}


@dataclass(slots=True)
class SeedCandidate:
    url: str
    domain: str
    lang: str
    region: str
    topic: str
    source: str
    value_prior: float
    tags: set[str] = field(default_factory=set)

    def to_json(self) -> Dict[str, object]:
        return {
            "url": self.url,
            "domain": self.domain,
            "lang": self.lang,
            "region": self.region,
            "topic": self.topic,
            "source": self.source,
            "value_prior": round(self.value_prior, 3),
            "tags": sorted(self.tags),
            "ts": int(time.time()),
        }


def _domain_from_url(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _tld(domain: str) -> str:
    parts = domain.split(".")
    return parts[-1] if len(parts) >= 2 else domain


def _guess_lang(domain: str, path: str) -> str:
    tld = _tld(domain)
    if tld in _LANG_BY_TLD:
        return _LANG_BY_TLD[tld]
    for segment in path.split("/"):
        seg = segment.lower()
        if seg in _LANG_BY_TLD:
            return _LANG_BY_TLD[seg]
        if len(seg) == 2 and seg.isalpha():
            return seg
    return "en"


def _guess_region(domain: str) -> str:
    lowered = domain.lower()
    for region, suffixes in _REGION_HINTS.items():
        if any(lowered.endswith(suffix) for suffix in suffixes):
            return region
    if lowered.endswith(".uk") or lowered.endswith(".ie"):
        return "eu"
    if lowered.endswith(".ca"):
        return "na"
    return "us"


def _topic_from_path(domain: str, path: str) -> str:
    tokens = [token for token in re.split(r"[^a-z0-9]+", f"{domain}{path}", flags=re.IGNORECASE) if token]
    if not tokens:
        return "general"
    common = {
        "www",
        "com",
        "docs",
        "documentation",
        "blog",
        "help",
        "support",
        "guide",
    }
    filtered = [token.lower() for token in tokens if token.lower() not in common]
    return filtered[0] if filtered else tokens[0].lower()


def _base_value(url: str, tags: set[str]) -> float:
    parsed = urlparse(url)
    score = 0.6
    path = parsed.path.lower()
    if any(keyword in path for keyword in _KEYWORDS_DOCS):
        score += 0.3
    if any(keyword in path for keyword in _KEYWORDS_COMMUNITY):
        score += 0.1
    if "api" in path:
        score += 0.1
    if parsed.netloc.lower().endswith(('.org', '.io', '.dev')):
        score += 0.1
    if "commoncrawl" in tags:
        score -= 0.1
    if "sitemap" in tags:
        score += 0.1
    return max(0.1, min(score, 1.5))


def _llm_enrichment(limit: int) -> List[SeedSource]:
    if not SMART_USE_LLM or llm_guess_urls is None:
        return []
    try:
        urls = llm_guess_urls(
            "diverse developer documentation sites", model=os.getenv("OLLAMA_MODEL")
        )
    except Exception as exc:  # pragma: no cover - best effort logging
        LOGGER.debug("LLM seed expansion failed: %s", exc)
        return []
    results: List[SeedSource] = []
    for url in urls[:limit]:
        results.append(SeedSource(url=url, source="llm:seed_guesser", tags={"llm"}))
    LOGGER.info("LLM proposed %d additional seed(s)", len(results))
    return results


def _dedupe(candidates: Iterable[SeedCandidate]) -> List[SeedCandidate]:
    seen: Dict[str, SeedCandidate] = {}
    for candidate in candidates:
        key = candidate.url.lower()
        existing = seen.get(key)
        if existing is None or candidate.value_prior > existing.value_prior:
            seen[key] = candidate
    return list(seen.values())


def curate_seeds(
    sources: Sequence[SeedSource],
    *,
    limit: int | None = None,
    non_en_quota: float | None = None,
    non_us_quota: float | None = None,
) -> List[SeedCandidate]:
    """Return curated, deduplicated seeds that satisfy diversity quotas."""

    target = limit or CURATED_LIMIT
    if target <= 0:
        return []
    non_en_target = max(0, min(1.0, non_en_quota if non_en_quota is not None else NON_EN_QUOTA))
    non_us_target = max(0, min(1.0, non_us_quota if non_us_quota is not None else NON_US_QUOTA))

    prepared: List[SeedCandidate] = []
    per_domain: Dict[str, int] = defaultdict(int)
    for source in sources:
        url = source.url
        domain = _domain_from_url(url)
        parsed = urlparse(url)
        path = parsed.path or "/"
        lang = _guess_lang(domain, path)
        region = _guess_region(domain)
        topic = _topic_from_path(domain, path)
        value = _base_value(url, source.tags)
        tags = set(source.tags)
        if lang != "en":
            tags.add("non_en")
        if region != "us":
            tags.add("non_us")
        candidate = SeedCandidate(
            url=url,
            domain=domain,
            lang=lang,
            region=region,
            topic=topic,
            source=source.source,
            value_prior=value,
            tags=tags,
        )
        if per_domain[domain] >= 3:
            continue
        per_domain[domain] += 1
        prepared.append(candidate)

    deduped = _dedupe(prepared)
    if not deduped:
        return []

    deduped.sort(key=lambda c: c.value_prior, reverse=True)

    required_non_en = math.ceil(target * non_en_target)
    required_non_us = math.ceil(target * non_us_target)

    selected: List[SeedCandidate] = []
    taken: set[str] = set()

    def _consume(pool: Iterable[SeedCandidate], quota: int) -> None:
        for candidate in pool:
            if len(selected) >= target:
                break
            if candidate.url in taken:
                continue
            selected.append(candidate)
            taken.add(candidate.url)
            if quota is not None:
                quota -= 1
                if quota <= 0:
                    break

    non_en_pool = [c for c in deduped if c.lang != "en"]
    non_us_pool = [c for c in deduped if c.region != "us"]

    _consume(non_en_pool, required_non_en)
    _consume(non_us_pool, required_non_us)
    _consume(deduped, None)

    if len(selected) > target:
        selected = selected[:target]

    return selected


def write_curated(candidates: Sequence[SeedCandidate], path: Path | None = None) -> Path:
    output_path = path or CURATED_PATH
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for candidate in candidates:
            handle.write(json.dumps(candidate.to_json(), ensure_ascii=False) + "\n")
    LOGGER.info("wrote %d curated seeds to %s", len(candidates), output_path)
    return output_path


def load_and_curate(curated_hosts: Sequence[str] | None = None) -> List[SeedCandidate]:
    """High level helper that loads sources, optionally augments via LLM, and curates."""

    sources = discover_sources(curated_hosts)
    sources.extend(_llm_enrichment(25))
    curated = curate_seeds(sources)
    write_curated(curated)
    return curated


__all__ = ["SeedCandidate", "curate_seeds", "load_and_curate", "write_curated"]
