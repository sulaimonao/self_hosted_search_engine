"""Agent maintainer policy loop (Plan → Patch → Verify → PR)."""

from __future__ import annotations

import enum
import re
from typing import Any, Dict, Mapping

from .agent_tools_repo import (
    git_branch,
    git_commit,
    git_diff,
    open_pr,
    repo_write_unified_diff,
    run_linters,
    run_perf_smoke,
    run_security_scan,
    run_tests,
)


class Autonomy(enum.IntEnum):
    """Operational modes for maintainer tasks."""

    OBSERVE = 0
    PATCH = 1
    MAINTAINER = 2


_BRANCH_PATTERN = re.compile(r"[^a-z0-9-]+")


def _sanitize_branch_name(task: str) -> str:
    slug = _BRANCH_PATTERN.sub("-", task.lower()).strip("-") or "task"
    return f"bot/{slug[:40]}"


def _coerce_autonomy(value: int | Autonomy) -> Autonomy:
    if isinstance(value, Autonomy):
        return value
    try:
        return Autonomy(int(value))
    except (ValueError, TypeError):  # pragma: no cover - defensive
        raise ValueError(f"invalid autonomy level: {value!r}")


def run_maintainer_task(
    task: str, autonomy: int | Autonomy = Autonomy.PATCH
) -> Dict[str, Any]:
    """Initialize a maintainer task by checking out a working branch."""

    if not task or not task.strip():
        raise ValueError("task description is required")
    level = _coerce_autonomy(autonomy)
    branch = _sanitize_branch_name(task)
    git_branch(branch)
    return {
        "status": "planned",
        "task": task,
        "branch": branch,
        "autonomy": int(level),
        "next": "apply_diff",
    }


def apply_and_verify(
    diff: str,
    autonomy: int | Autonomy = Autonomy.PATCH,
    *,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Apply a diff (unless dry-run) and execute verification gates."""

    level = _coerce_autonomy(autonomy)
    if level == Autonomy.OBSERVE:
        return {
            "ok": False,
            "autonomy": int(level),
            "error": "Autonomy=OBSERVE blocks repository writes",
        }
    if not diff or not diff.strip():
        return {"ok": False, "autonomy": int(level), "error": "diff content required"}

    try:
        if not dry_run:
            repo_write_unified_diff(diff)
        lint = run_linters()
        tests = run_tests()
        security = run_security_scan()
        perf = run_perf_smoke()
        overall = bool(
            lint.get("ok") and tests.get("ok") and security.get("ok") and perf.get("ok")
        )
        result: Dict[str, Any] = {
            "ok": overall,
            "lint": lint,
            "tests": tests,
            "security": security,
            "perf": perf,
            "autonomy": int(level),
        }
        if not dry_run:
            result["diff"] = git_diff()
        else:
            result["dry_run"] = True
        return result
    except Exception as exc:  # pragma: no cover - surface tool errors
        return {"ok": False, "autonomy": int(level), "error": str(exc)}


def finalize_pr(title: str, body: str) -> Mapping[str, Any]:
    """Commit staged changes and open a pull request via the GH CLI."""

    clean_title = (title or "").strip()
    if not clean_title:
        raise ValueError("commit/PR title is required")
    git_commit(clean_title)
    payload = open_pr(clean_title, body)
    payload.setdefault("title", clean_title)
    return payload


__all__ = ["Autonomy", "apply_and_verify", "finalize_pr", "run_maintainer_task"]
