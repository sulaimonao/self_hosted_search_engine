from __future__ import annotations

from functools import lru_cache
from typing import Any, Callable, Sequence

from pydantic import ValidationError

from .models import Directive, Incident, Step


ModelResolver = Callable[[str], str | None]


def _safe_validate(model_cls: type[Directive] | type[Incident] | type[Step], payload: Any):
    try:
        return model_cls.model_validate(payload)
    except ValidationError:
        return model_cls()  # type: ignore[call-arg]


def coerce_incident(payload: Any) -> Incident:
    if isinstance(payload, Incident):
        return payload
    if payload is None:
        return Incident()
    return _safe_validate(Incident, payload)


def coerce_directive(payload: Any) -> Directive:
    if isinstance(payload, Directive):
        return payload
    if payload is None:
        return Directive()
    directive = _safe_validate(Directive, payload)
    return directive


def _normalize_token(value: str) -> str:
    token = value.strip().lower()
    for ch in (" ", "-", "_", ":", ".", "/"):
        token = token.replace(ch, "")
    return token


@lru_cache(maxsize=None)
def _alias_map() -> dict[str, str]:
    aliases: dict[str, Sequence[str]] = {
        "gpt-oss": (
            "gpt-oss",
            "gpt",
            "gptoss",
            "gpt-4",
            "gpt4",
            "gpt4mini",
            "gpt-4mini",
            "gpt4mini-gguf",
        ),
        "gemma3": (
            "gemma3",
            "gemma",
            "gemma2b",
            "gemma-2b",
            "gemma:2b",
            "gemma-3",
            "gemma3instruct",
        ),
    }
    mapping: dict[str, str] = {}
    for canonical, variations in aliases.items():
        canonical_token = _normalize_token(canonical)
        mapping[canonical_token] = canonical
        for alias in variations:
            mapping[_normalize_token(alias)] = canonical
    return mapping


def _resolve_candidate(candidate: str, resolver: ModelResolver | None) -> str | None:
    if resolver is None:
        return None
    try:
        resolved = resolver(candidate)
    except Exception:
        return None
    if not resolved:
        return None
    token = _normalize_token(resolved)
    mapping = _alias_map()
    if token in mapping:
        return mapping[token]
    if token.startswith("gemma"):
        return "gemma3"
    if token.startswith("gpt"):
        return "gpt-oss"
    return None


def _canonical(candidate: str, resolver: ModelResolver | None) -> str | None:
    token = _normalize_token(candidate)
    if not token:
        return None
    mapping = _alias_map()
    if token in mapping:
        return mapping[token]
    if token.startswith("gemma"):
        return "gemma3"
    if token.startswith("gpt"):
        return "gpt-oss"
    return _resolve_candidate(candidate, resolver)


def normalize_model(
    name: str | None,
    *,
    resolver: ModelResolver | None = None,
    configured: Sequence[str] | None = None,
) -> str:
    candidates: list[str] = []
    if isinstance(name, str):
        trimmed = name.strip()
        if trimmed:
            candidates.append(trimmed)
    if configured:
        for item in configured:
            if isinstance(item, str) and item.strip():
                candidates.append(item.strip())
    candidates.extend(["gpt-oss", "gemma3"])
    for candidate in candidates:
        canonical = _canonical(candidate, resolver)
        if canonical in ("gpt-oss", "gemma3"):
            return canonical
    fallback = _resolve_candidate("gpt-oss", resolver)
    return fallback or "gpt-oss"


__all__ = [
    "coerce_directive",
    "coerce_incident",
    "normalize_model",
]
