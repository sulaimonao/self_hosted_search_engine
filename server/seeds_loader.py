"""Utilities for loading curated seed source registry definitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, List, Mapping, MutableMapping, Sequence
from urllib.parse import urlparse

import yaml

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_REGISTRY_PATH = ROOT_DIR / "seeds" / "registry.yaml"


@dataclass(frozen=True)
class SeedRegistryEntry:
    """Normalized configuration for a seed discovery source."""

    id: str
    kind: str
    strategy: str
    entrypoints: tuple[str, ...]
    trust: float | str
    extras: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a plain dictionary representation of the entry."""

        payload: dict[str, Any] = {
            "id": self.id,
            "kind": self.kind,
            "strategy": self.strategy,
            "entrypoints": list(self.entrypoints),
            "trust": self.trust,
        }
        payload.update(self.extras)
        return payload


def _ensure_mapping(node: Any) -> Mapping[str, Any]:
    if not isinstance(node, MutableMapping):
        raise TypeError(f"expected mapping entries, got {type(node)!r}")
    return node


def _normalize_id(value: Any) -> str:
    if value is None:
        raise ValueError("registry entry is missing required 'id'")
    text = str(value).strip()
    if not text:
        raise ValueError("registry entry 'id' cannot be empty")
    return text


def _normalize_simple_field(value: Any, name: str) -> str:
    if value is None:
        raise ValueError(f"registry entry is missing required '{name}'")
    text = str(value).strip()
    if not text:
        raise ValueError(f"registry entry '{name}' cannot be empty")
    return text.lower()


def _normalize_entrypoints(value: Any) -> tuple[str, ...]:
    if value is None:
        raise ValueError("registry entry requires at least one entrypoint")

    if isinstance(value, (str, bytes)):
        candidates: Iterable[Any] = [value]
    elif isinstance(value, Sequence):
        candidates = value
    else:
        raise TypeError("entrypoints must be a string or sequence of strings")

    normalized: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if isinstance(candidate, Mapping):
            url_candidate = candidate.get("url")
        else:
            url_candidate = candidate
        if url_candidate is None:
            continue
        url_text = str(url_candidate).strip()
        if not url_text:
            continue
        parsed = urlparse(url_text)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError(f"invalid entrypoint URL '{url_text}'")
        if url_text not in seen:
            normalized.append(url_text)
            seen.add(url_text)

    if not normalized:
        raise ValueError("registry entry must define at least one valid entrypoint")
    return tuple(normalized)


def _normalize_trust(value: Any) -> float | str:
    if value is None:
        return "medium"
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError("registry entry 'trust' cannot be empty")
        lowered = text.lower()
        if lowered in {"low", "medium", "high"}:
            return lowered
        try:
            return float(text)
        except ValueError as exc:  # pragma: no cover - defensive fallback
            raise ValueError(f"invalid trust value '{value}'") from exc
    raise TypeError("trust must be a string or numeric value")


def _normalize_entry(raw: Mapping[str, Any]) -> SeedRegistryEntry:
    data = dict(raw)
    entry_id = _normalize_id(data.pop("id", None))
    kind = _normalize_simple_field(data.pop("kind", None), "kind")
    strategy = _normalize_simple_field(data.pop("strategy", None), "strategy")
    entrypoints = _normalize_entrypoints(data.pop("entrypoints", None))
    trust = _normalize_trust(data.pop("trust", None))
    extras = {key: value for key, value in data.items() if value is not None}
    return SeedRegistryEntry(
        id=entry_id,
        kind=kind,
        strategy=strategy,
        entrypoints=entrypoints,
        trust=trust,
        extras=extras,
    )


def load_seed_registry(path: str | Path | None = None) -> List[SeedRegistryEntry]:
    """Load and normalize registry entries from ``seeds/registry.yaml``."""

    registry_path = Path(path) if path else DEFAULT_REGISTRY_PATH
    if not registry_path.exists():
        return []

    with registry_path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}

    if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes)):
        raw_entries = payload
    else:
        mapping = _ensure_mapping(payload)
        raw_entries = mapping.get("sources", [])

    entries: List[SeedRegistryEntry] = []
    seen_ids: set[str] = set()
    for item in raw_entries:
        entry = _normalize_entry(_ensure_mapping(item))
        if entry.id in seen_ids:
            raise ValueError(f"duplicate seed registry id '{entry.id}'")
        entries.append(entry)
        seen_ids.add(entry.id)
    return entries


__all__ = ["DEFAULT_REGISTRY_PATH", "SeedRegistryEntry", "load_seed_registry"]
