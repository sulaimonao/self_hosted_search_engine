"""Thin wrappers for interacting with the agent browser executor."""

from __future__ import annotations

from typing import Iterable, Mapping, Optional

from backend.app.exec.headless_executor import HeadlessResult, run as _run_directive


def run_headless(
    steps: Iterable[Mapping[str, object]],
    *,
    base_url: str,
    session_id: Optional[str] = None,
    sse_publish=None,
) -> HeadlessResult:
    """Execute planner steps via the headless executor.

    Parameters
    ----------
    steps:
        Iterable of directive steps. Non-mapping entries are ignored. Any
        additional metadata (e.g. ``headless``) is preserved for downstream
        filtering within :mod:`backend.app.exec.headless_executor`.
    base_url:
        Host used to reach the agent browser API.
    session_id:
        Optional pre-existing agent browser session identifier.
    sse_publish:
        Optional callback for streaming progress events.

    Returns
    -------
    HeadlessResult
        Structured execution result as returned by the underlying executor.
    """

    payload_steps = [dict(step) for step in steps if isinstance(step, Mapping)]
    directive = {"steps": payload_steps}
    return _run_directive(
        directive,
        base_url=base_url,
        sse_publish=sse_publish,
        session_id=session_id,
    )


__all__ = ["run_headless"]
