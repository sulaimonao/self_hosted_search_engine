from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Callable, Mapping, Sequence

from pydantic import ValidationError

from .models import ALLOWED_VERBS, Directive, Incident, Step


ModelResolver = Callable[[str], str | None]

_DEFAULT_MODEL_ALIAS = "gpt-oss:20b"
_ALLOWED_MODEL_ALIASES: dict[str, Sequence[str]] = {
    "gpt-oss:20b": (
        "gpt-oss",
        "gptoss",
        "gpt",
        "gpt-4",
        "gpt4",
        "gpt4mini",
        "gpt-4mini",
        "gpt4mini-gguf",
        "gpt-oss20b",
        "gptoss20b",
        "gpt-oss:20b",
    ),
    "gemma3:latest": (
        "gemma3",
        "gemma-3",
        "gemma 3",
        "gemma",
        "gemma2b",
        "gemma:2b",
        "gemma3instruct",
        "gemma3:latest",
    ),
}


@dataclass(slots=True)
class DirectiveClampResult:
    """Container describing directive normalization results."""

    directive: Directive
    dropped_steps: list[str]
    fallback_applied: bool

    def as_payload(self) -> dict[str, Any]:
        return self.directive.as_payload()


def _ensure_mapping(payload: Any) -> dict[str, Any]:
    if isinstance(payload, Directive):
        return payload.model_dump(mode="json", by_alias=True)
    if isinstance(payload, Mapping):
        return dict(payload)
    if isinstance(payload, str):
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            return {"reason": payload}
        if isinstance(parsed, Mapping):
            return dict(parsed)
    return {}


def _safe_validate(model_cls: type[Directive] | type[Incident] | type[Step], payload: Any):
    try:
        return model_cls.model_validate(payload)
    except ValidationError:
        return model_cls()  # type: ignore[call-arg]


def _coerce_str(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)):
        return str(value).strip()
    return ""


def clamp_incident(payload: Any) -> Incident:
    """Clamp a raw incident payload to the validated Incident model."""

    if isinstance(payload, Incident):
        source = payload.model_dump(mode="json", by_alias=True)
    elif isinstance(payload, Mapping):
        source = dict(payload)
    elif isinstance(payload, str):
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            source = {"url": payload}
        else:
            source = dict(parsed) if isinstance(parsed, Mapping) else {}
    else:
        source = {}

    try:
        return Incident.model_validate(source)
    except ValidationError:
        return Incident()


def clamp_directive(payload: Any, *, fallback_reason: str | None = None) -> DirectiveClampResult:
    """Normalize planner responses down to executor-safe directives."""

    raw = _ensure_mapping(payload)
    steps_in = raw.get("steps")
    sanitized_steps: list[Step] = []
    dropped: list[str] = []
    if isinstance(steps_in, Sequence) and not isinstance(steps_in, (str, bytes, bytearray)):
        for idx, candidate in enumerate(steps_in, start=1):
            try:
                step_model = Step.model_validate(candidate)
            except ValidationError:
                dropped.append(f"step_{idx}:invalid")
                continue
            if step_model.type not in ALLOWED_VERBS:
                dropped.append(f"step_{idx}:verb")
                continue
            sanitized_steps.append(step_model)
    elif steps_in not in (None, []):
        dropped.append("steps:invalid")

    fallback_applied = not sanitized_steps
    if fallback_applied:
        sanitized_steps = [Step(type="reload")]

    reason = _coerce_str(raw.get("reason")) or ("Planned fix" if not fallback_applied else "timeout_or_invalid")
    if fallback_applied and fallback_reason:
        reason = fallback_reason

    directive_payload = dict(raw)
    directive_payload["reason"] = reason
    directive_payload["steps"] = sanitized_steps

    try:
        directive = Directive.model_validate(directive_payload)
    except ValidationError:
        directive = Directive(reason=reason, steps=sanitized_steps)

    return DirectiveClampResult(directive=directive, dropped_steps=dropped, fallback_applied=fallback_applied)


def coerce_incident(payload: Any) -> Incident:
    return clamp_incident(payload)


def coerce_directive(payload: Any) -> Directive:
    return clamp_directive(payload).directive


def _normalize_token(value: str) -> str:
    token = value.strip().lower()
    for ch in (" ", "-", "_", ":", ".", "/"):
        token = token.replace(ch, "")
    return token


@lru_cache(maxsize=None)
def _model_alias_map() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for canonical, aliases in _ALLOWED_MODEL_ALIASES.items():
        for alias in aliases:
            mapping[_normalize_token(alias)] = canonical
        mapping[_normalize_token(canonical)] = canonical
    return mapping


def allowed_model_aliases() -> tuple[str, ...]:
    return tuple(sorted(_ALLOWED_MODEL_ALIASES))


def normalize_model_alias(name: str | None, *, default: str = _DEFAULT_MODEL_ALIAS) -> str:
    if name is None:
        return default
    token = _normalize_token(name)
    if not token:
        return default
    mapping = _model_alias_map()
    if token in mapping:
        return mapping[token]
    raise ValueError(f"Unsupported model alias '{name}'. Allowed: {', '.join(allowed_model_aliases())}")


def normalize_model(
    name: str | None,
    *,
    resolver: ModelResolver | None = None,
    configured: Sequence[str] | None = None,
) -> str:
    try:
        alias = normalize_model_alias(name)
    except ValueError:
        alias = normalize_model_alias(None)
    if alias.startswith("gemma3"):
        return "gemma3"
    return "gpt-oss"


__all__ = [
    "DirectiveClampResult",
    "allowed_model_aliases",
    "clamp_directive",
    "clamp_incident",
    "coerce_directive",
    "coerce_incident",
    "normalize_model",
    "normalize_model_alias",
]
