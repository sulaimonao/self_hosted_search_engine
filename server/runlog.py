"""Collect short run-log entries for planner transparency."""

from __future__ import annotations

from typing import List, Optional

try:  # pragma: no cover - optional dependency on Flask request context
    from flask import g, has_app_context, has_request_context
except Exception:  # pragma: no cover - allows import without Flask context
    g = None  # type: ignore

    def has_app_context() -> bool:  # type: ignore
        return False

    def has_request_context() -> bool:  # type: ignore
        return False


class RunLog:
    """In-memory accumulator for per-request run log lines."""

    def __init__(self) -> None:
        self.lines: List[str] = []

    def add(self, entry: str) -> None:
        if not entry:
            return
        self.lines.append(str(entry))

    def extend(self, entries: List[str]) -> None:
        for entry in entries:
            self.add(entry)

    def dump(self) -> List[str]:
        return list(self.lines)


def _get_g() -> Optional[object]:  # pragma: no cover - thin wrapper
    if g is None:
        return None
    try:
        if not (has_request_context() or has_app_context()):
            return None
    except RuntimeError:
        return None
    return g


def current_run_log(create: bool = False) -> Optional[RunLog]:
    """Return the run log bound to ``flask.g`` if available."""

    flask_g = _get_g()
    if flask_g is None:
        return None
    log = getattr(flask_g, "run_log", None)
    if log is None and create:
        log = RunLog()
        setattr(flask_g, "run_log", log)
    return log


def add_run_log_line(message: str) -> None:
    log = current_run_log(create=False)
    if log is not None:
        log.add(message)


__all__ = ["RunLog", "current_run_log", "add_run_log_line"]
