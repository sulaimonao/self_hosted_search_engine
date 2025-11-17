"""Safe repository interaction endpoints for AI tooling."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from flask import Blueprint, abort, current_app, jsonify, request

from backend.app.db import AppStateDB

try:  # pragma: no cover - fallback when script is missing
    from scripts import change_budget as change_budget_guard
except Exception:  # pragma: no cover - conservative fallback
    change_budget_guard = None

MAX_FILES = getattr(change_budget_guard, "MAX_FILES", 50)
MAX_LOC = getattr(change_budget_guard, "MAX_LOC", 4000)

bp = Blueprint("repo_api", __name__, url_prefix="/api/repo")


def _state_db() -> AppStateDB:
    state_db = current_app.config.get("APP_STATE_DB")
    if not isinstance(state_db, AppStateDB):  # pragma: no cover - misconfiguration
        abort(500, "app state database unavailable")
    return state_db


def _get_repo(repo_id: str) -> dict[str, Any]:
    state_db = _state_db()
    record = state_db.get_repo(repo_id)
    if not record:
        abort(404, f"repo {repo_id} not found")
    return record


def _git_status_summary(root_path: Path) -> dict[str, Any]:
    try:
        status_proc = subprocess.run(  # noqa: S603,S607 - trusted git invocation
            ["git", "status", "--short", "--branch"],
            cwd=root_path,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        lines = [line.strip() for line in status_proc.stdout.splitlines() if line.strip()]
    except (OSError, subprocess.SubprocessError):
        return {"error": "git_status_failed"}
    branch = "unknown"
    dirty = False
    ahead: int | None = None
    behind: int | None = None
    if lines:
        head = lines[0]
        if head.startswith("##"):
            branch = head[2:].strip()
            if "ahead" in branch:
                try:
                    ahead = int(branch.split("ahead ")[-1].split(")")[0])
                except ValueError:
                    ahead = None
            if "behind" in branch:
                try:
                    behind = int(branch.split("behind ")[-1].split(")")[0])
                except ValueError:
                    behind = None
    dirty = any(not line.startswith("##") for line in lines)
    short = [line for line in lines if not line.startswith("##")][:100]
    return {
        "branch": branch,
        "dirty": dirty,
        "ahead": ahead,
        "behind": behind,
        "changes": short,
    }


def _count_diff_lines(diff: str) -> tuple[int, int]:
    additions = 0
    deletions = 0
    for line in diff.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            additions += 1
        elif line.startswith("-"):
            deletions += 1
    return additions, deletions


def _validate_file_entry(entry: Any, *, repo_root: Path) -> dict[str, Any]:
    if not isinstance(entry, dict):
        abort(400, "each file entry must be an object")
    raw_path = str(entry.get("path") or "").strip()
    if not raw_path:
        abort(400, "file path is required")
    candidate = Path(raw_path)
    if candidate.is_absolute():
        abort(400, "file path must be relative")
    normalized = candidate
    resolved = (repo_root / normalized).resolve()
    try:
        resolved.relative_to(repo_root.resolve())
    except ValueError:
        abort(400, "file path escapes repository root")
    diff = entry.get("diff")
    if diff is not None:
        diff_text = str(diff)
    else:
        diff_text = ""
    additions = int(entry.get("additions") or 0)
    deletions = int(entry.get("deletions") or 0)
    if not additions and not deletions and diff_text:
        adds, dels = _count_diff_lines(diff_text)
        additions, deletions = adds, dels
    return {
        "path": raw_path,
        "resolved_path": str(resolved),
        "diff": diff_text or None,
        "additions": additions,
        "deletions": deletions,
    }


def _validate_budget(files: list[dict[str, Any]]) -> tuple[int, int]:
    total_lines = sum(max(0, item["additions"]) + max(0, item["deletions"]) for item in files)
    if len(files) > MAX_FILES:
        response = jsonify(
            {"error": "budget_exceeded", "detail": f"file limit {MAX_FILES} exceeded"}
        )
        response.status_code = 400
        abort(response)
    if total_lines > MAX_LOC:
        response = jsonify(
            {"error": "budget_exceeded", "detail": f"line delta limit {MAX_LOC} exceeded"}
        )
        response.status_code = 400
        abort(response)
    return len(files), total_lines


@bp.get("/list")
def list_repos() -> Any:
    state_db = _state_db()
    return jsonify({"items": state_db.list_repos()})


@bp.get("/<repo_id>/status")
def repo_status(repo_id: str):
    record = _get_repo(repo_id)
    root = Path(record["root_path"])
    summary = _git_status_summary(root)
    summary.update({"repo_id": repo_id, "root_path": str(root)})
    return jsonify(summary)


@bp.post("/<repo_id>/propose_patch")
def propose_patch(repo_id: str):
    record = _get_repo(repo_id)
    if "write" not in record.get("allowed_ops", []):
        abort(403, "write operations are disabled for this repository")
    payload = request.get_json(force=True, silent=True) or {}
    files = payload.get("files")
    if not isinstance(files, list) or not files:
        abort(400, "files list is required")
    repo_root = Path(record["root_path"]).resolve()
    validated = [_validate_file_entry(item, repo_root=repo_root) for item in files]
    file_count, total_lines = _validate_budget(validated)
    response = {
        "accepted": True,
        "files": [
            {
                "path": item["path"],
                "additions": item["additions"],
                "deletions": item["deletions"],
            }
            for item in validated
        ],
        "budget": {
            "files": file_count,
            "lines": total_lines,
            "max_files": MAX_FILES,
            "max_lines": MAX_LOC,
        },
        "message": "proposal validated; apply_patch TODO",
    }
    return jsonify(response), 202


def apply_patch(*_args: Any, **_kwargs: Any) -> None:  # pragma: no cover - future work stub
    """Placeholder for repo patch application logic."""
    raise NotImplementedError("apply_patch is not implemented yet")

