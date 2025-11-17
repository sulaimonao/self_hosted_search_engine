"""Safe repository interaction endpoints for AI tooling."""

from __future__ import annotations

from contextlib import suppress
from datetime import datetime, timezone
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Iterable

from flask import Blueprint, abort, current_app, jsonify, request

from backend.app.db import AppStateDB

try:  # pragma: no cover - fallback when script is missing
    from scripts import change_budget as change_budget_guard
except Exception:  # pragma: no cover - conservative fallback
    change_budget_guard = None

MAX_FILES = getattr(change_budget_guard, "MAX_FILES", 50)
MAX_LOC = getattr(change_budget_guard, "MAX_LOC", 4000)

bp = Blueprint("repo_api", __name__, url_prefix="/api/repo")


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")


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


def _normalize_command_arg(command: Any) -> list[str] | None:
    if command is None:
        return None
    if isinstance(command, str):
        candidate = command.strip()
        return [candidate] if candidate else None
    if isinstance(command, Iterable):
        tokens: list[str] = []
        for entry in command:
            if entry is None:
                continue
            text = str(entry).strip()
            if not text:
                continue
            tokens.append(text)
        return tokens or None
    return None


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


def _write_atomic_text(target: Path, content: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_file: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=str(target.parent), delete=False
        ) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
            tmp_file = Path(handle.name)
        tmp_file.replace(target)
    finally:
        if tmp_file is not None and tmp_file.exists():
            with suppress(OSError):
                tmp_file.unlink()


def _apply_file_changes(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    applied: list[dict[str, Any]] = []
    for entry in files:
        resolved = Path(entry["resolved_path"])
        resolved.parent.mkdir(parents=True, exist_ok=True)
        action: str
        if entry.get("delete"):
            action = "deleted"
            with suppress(FileNotFoundError):
                resolved.unlink()
        else:
            content = entry.get("content")
            if content is None:
                abort(400, f"content required for {entry['path']}")
            _write_atomic_text(resolved, str(content))
            action = "updated"
        applied.append({"path": entry["path"], "action": action})
    return applied


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


@bp.post("/<repo_id>/apply_patch")
def apply_patch_endpoint(repo_id: str):
    record = _get_repo(repo_id)
    if "write" not in record.get("allowed_ops", []):
        abort(403, "write operations are disabled for this repository")
    payload = request.get_json(force=True, silent=True) or {}
    files = payload.get("files")
    if not isinstance(files, list) or not files:
        abort(400, "files list is required")
    summary = (payload.get("summary") or "").strip() or None
    repo_root = Path(record["root_path"]).resolve()
    validated: list[dict[str, Any]] = []
    for entry in files:
        file_data = _validate_file_entry(entry, repo_root=repo_root)
        delete_flag = bool(entry.get("delete"))
        file_data["delete"] = delete_flag
        if not delete_flag:
            content = entry.get("content")
            if content is None:
                abort(400, f"content required for {file_data['path']}")
            file_data["content"] = str(content)
        validated.append(file_data)
    file_count, total_lines = _validate_budget(validated)
    state_db = _state_db()
    job_payload = {
        "repo_id": repo_id,
        "file_count": file_count,
        "line_delta": total_lines,
        "summary": summary,
    }
    job_id = state_db.create_job("repo_apply_patch", payload=job_payload)
    state_db.update_job(job_id, status="running", started_at=_now_iso())
    change_stats = {
        "files": file_count,
        "lines": total_lines,
        "details": [
            {
                "path": item["path"],
                "additions": item["additions"],
                "deletions": item["deletions"],
                "delete": bool(item.get("delete")),
            }
            for item in validated
        ],
    }
    try:
        applied = _apply_file_changes(validated)
    except Exception as exc:  # pragma: no cover - defensive logging
        state_db.update_job(
            job_id,
            status="failed",
            error=str(exc),
            completed_at=_now_iso(),
        )
        state_db.record_repo_change(
            repo_id,
            summary=summary or "apply_patch failed",
            change_stats=change_stats,
            result="failed",
            error_message=str(exc),
            job_id=job_id,
        )
        abort(500, "failed to apply patch")
    result_payload = {
        "files": applied,
        "change_stats": change_stats,
        "summary": summary or f"Applied {file_count} file(s)",
    }
    state_db.update_job(
        job_id,
        status="succeeded",
        completed_at=_now_iso(),
        result=result_payload,
    )
    state_db.record_repo_change(
        repo_id,
        summary=result_payload["summary"],
        change_stats=change_stats,
        result="succeeded",
        error_message=None,
        job_id=job_id,
    )
    response = dict(result_payload)
    response.update({"job_id": job_id, "repo_id": repo_id})
    return jsonify(response)


def _truncate_output(text: str, limit: int = 16000) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _resolve_check_command(record: dict[str, Any], override: Any) -> list[str]:
    configured = _normalize_command_arg(record.get("check_command")) or []
    override_cmd = _normalize_command_arg(override)
    if override_cmd and override_cmd != configured:
        response = jsonify(
            {
                "error": "command_not_allowed",
                "detail": "command overrides must match the configured check command",
            }
        )
        response.status_code = 400
        abort(response)
    return configured


@bp.post("/<repo_id>/run_checks")
def run_checks(repo_id: str):
    record = _get_repo(repo_id)
    allowed = {op for op in record.get("allowed_ops", [])}
    if not ({"write", "run_checks", "checks"} & allowed):
        abort(403, "check operations are disabled for this repository")
    payload = request.get_json(force=True, silent=True) or {}
    command = _resolve_check_command(record, payload.get("command"))
    if not command:
        response = jsonify(
            {"error": "no check command configured for this repository"}
        )
        response.status_code = 400
        return response
    timeout_value = payload.get("timeout")
    if timeout_value is None:
        timeout_seconds = 600.0
    else:
        try:
            timeout_seconds = float(timeout_value)
        except (TypeError, ValueError):
            abort(400, "timeout must be numeric")
        if timeout_seconds <= 0:
            abort(400, "timeout must be positive")
    repo_root = Path(record["root_path"]).resolve()
    summary = (payload.get("summary") or "").strip() or f"Run {' '.join(command)}"
    state_db = _state_db()
    job_id = state_db.create_job(
        "repo_run_checks",
        payload={
            "repo_id": repo_id,
            "command": command,
            "timeout": timeout_seconds,
            "summary": summary,
        },
    )
    started_at = _now_iso()
    state_db.update_job(job_id, status="running", started_at=started_at)
    try:
        proc = subprocess.run(  # noqa: S603,S607 - trusted command
            command,
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        error_message = f"timeout after {timeout_seconds}s"
        state_db.update_job(
            job_id,
            status="failed",
            error=error_message,
            completed_at=_now_iso(),
        )
        state_db.record_repo_change(
            repo_id,
            summary=summary,
            change_stats={"command": command, "timeout": timeout_seconds},
            result="failed",
            error_message=error_message,
            job_id=job_id,
        )
        abort(504, error_message)
    except Exception as exc:  # pragma: no cover - defensive path
        error_message = str(exc)
        state_db.update_job(
            job_id,
            status="failed",
            error=error_message,
            completed_at=_now_iso(),
        )
        state_db.record_repo_change(
            repo_id,
            summary=summary,
            change_stats={"command": command},
            result="failed",
            error_message=error_message,
            job_id=job_id,
        )
        abort(500, "run_checks_failed")
    output_chunks = [proc.stdout or "", proc.stderr or ""]
    combined_output = "\n".join(chunk for chunk in output_chunks if chunk)
    truncated = _truncate_output(combined_output)
    completed_at = _now_iso()
    result_status = "succeeded" if proc.returncode == 0 else "failed"
    result_payload = {
        "repo_id": repo_id,
        "command": command,
        "exit_code": proc.returncode,
        "output": truncated,
        "started_at": started_at,
        "completed_at": completed_at,
        "timeout": timeout_seconds,
        "status": result_status,
    }
    state_db.update_job(
        job_id,
        status=result_status,
        completed_at=completed_at,
        result=result_payload,
        error=None if result_status == "succeeded" else truncated[-200:],
    )
    state_db.record_repo_change(
        repo_id,
        summary=f"Checks exit {proc.returncode}",
        change_stats={"command": command, "exit_code": proc.returncode},
        result=result_status,
        error_message=None if result_status == "succeeded" else truncated[:500],
        job_id=job_id,
    )
    response = dict(result_payload)
    response["job_id"] = job_id
    return jsonify(response)

