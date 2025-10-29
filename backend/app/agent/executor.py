"""Thin wrappers for interacting with the agent browser executor."""

from __future__ import annotations

import os
from typing import Any, Iterable, Mapping, Optional

from backend.app.exec.headless_executor import HeadlessResult, run as _run_directive

_DEFAULT_MAX_STEPS = 12


def _coerce_directive(payload: Any) -> dict[str, Any]:
    if isinstance(payload, Mapping):
        return dict(payload)
    if isinstance(payload, Iterable):
        steps = [dict(step) for step in payload if isinstance(step, Mapping)]
        return {"steps": steps}
    return {"steps": []}


def _max_steps() -> int:
    raw = os.environ.get("SELF_HEAL_HEADLESS_MAX_STEPS")
    if raw is None:
        return _DEFAULT_MAX_STEPS
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return _DEFAULT_MAX_STEPS
    if value <= 0:
        return _DEFAULT_MAX_STEPS
    return value


def run_headless(
    directive: Mapping[str, Any] | Iterable[Mapping[str, Any]],
    *,
    base_url: str,
    session_id: Optional[str] = None,
    sse_publish=None,
) -> HeadlessResult:
    """Execute planner directives via the headless executor."""

    directive_payload = _coerce_directive(directive)
    return _run_directive(
        directive_payload,
        base_url=base_url,
        sse_publish=sse_publish,
        session_id=session_id,
        max_steps=_max_steps(),
    )


__all__ = ["run_headless"]
