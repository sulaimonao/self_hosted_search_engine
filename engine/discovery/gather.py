"""Registry loader that coordinates discovery strategies."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, Iterable, List
from urllib.parse import urlparse

from server.seeds_loader import SeedRegistryEntry, load_seed_registry

from .strategies import STRATEGY_REGISTRY, StrategyCandidate

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class RegistryCandidate:
    """Normalized candidate surfaced from the registry."""

    url: str
    score: float
    source: str
    strategy: str
    entry_id: str
    title: str | None = None
    summary: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "url": self.url,
            "score": self.score,
            "source": self.source,
            "strategy": self.strategy,
            "entry_id": self.entry_id,
        }
        if self.title:
            payload["title"] = self.title
        if self.summary:
            payload["summary"] = self.summary
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload


def _sanitize_url(url: str) -> str | None:
    candidate = (url or "").strip()
    if not candidate:
        return None
    parsed = urlparse(candidate)
    if not parsed.scheme:
        if candidate.startswith("//"):
            candidate = "https:" + candidate
        else:
            candidate = "https://" + candidate.lstrip("/")
        parsed = urlparse(candidate)
    if not parsed.scheme or not parsed.netloc:
        return None
    scheme = parsed.scheme if parsed.scheme in {"http", "https"} else "https"
    path = parsed.path or "/"
    sanitized = f"{scheme}://{parsed.netloc}{path}"
    if parsed.query:
        sanitized = f"{sanitized}?{parsed.query}"
    return sanitized.rstrip("/")


def _trust_multiplier(value: object) -> float:
    if isinstance(value, (int, float)):
        return max(0.1, float(value))
    if isinstance(value, str):
        text = value.strip().lower()
        if not text:
            return 1.0
        if text == "low":
            return 0.85
        if text == "medium":
            return 1.0
        if text == "high":
            return 1.2
        try:
            return max(0.1, float(text))
        except ValueError:
            return 1.0
    return 1.0


def _coerce_float(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _score_with_trust(raw_score: float, trust: object, extras: dict[str, object]) -> float:
    base = float(raw_score) if raw_score is not None else 0.0
    if base <= 0:
        base = 0.05
    multiplier = _trust_multiplier(trust)
    boost = _coerce_float(extras.get("boost")) if isinstance(extras, dict) else None
    if boost is not None and boost > 0:
        multiplier *= boost
    return base * multiplier


def _collect_candidates(
    *,
    entry: SeedRegistryEntry,
    query: str,
    limit: int,
) -> Iterable[StrategyCandidate]:
    strategy = STRATEGY_REGISTRY.get(entry.strategy)
    if strategy is None:
        LOGGER.debug("unknown registry strategy '%s'", entry.strategy)
        return []
    try:
        return strategy(entry, query, limit)
    except Exception:  # pragma: no cover - defensive logging
        LOGGER.debug("strategy %s failed for %s", entry.strategy, entry.id, exc_info=True)
        return []


def gather_from_registry(query: str, max_candidates: int = 10) -> List[RegistryCandidate]:
    """Run configured registry strategies for ``query`` and dedupe results."""

    clean_query = (query or "").strip()
    if not clean_query:
        return []
    cap = max(1, int(max_candidates))
    entries = load_seed_registry()
    if not entries:
        return []

    deduped: Dict[str, RegistryCandidate] = {}
    for entry in entries:
        raw_candidates = _collect_candidates(entry=entry, query=clean_query, limit=cap)
        if not raw_candidates:
            continue
        base_metadata = {"trust": entry.trust}
        base_metadata.update(entry.extras)
        for candidate in raw_candidates:
            sanitized = _sanitize_url(candidate.url)
            if not sanitized:
                continue
            score = _score_with_trust(candidate.score, entry.trust, entry.extras)
            metadata = dict(base_metadata)
            metadata.update(candidate.metadata)
            result = RegistryCandidate(
                url=sanitized,
                score=score,
                source=f"registry:{entry.id}",
                strategy=entry.strategy,
                entry_id=entry.id,
                title=candidate.title,
                summary=candidate.summary,
                metadata=metadata,
            )
            existing = deduped.get(sanitized)
            if existing is None or result.score > existing.score:
                deduped[sanitized] = result
    ordered = sorted(deduped.values(), key=lambda item: item.score, reverse=True)
    return ordered[:cap]


__all__ = ["RegistryCandidate", "gather_from_registry"]
