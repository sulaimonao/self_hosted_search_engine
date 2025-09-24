"""System diagnostics job producing repository and runtime metadata."""

from __future__ import annotations

import datetime as _dt
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

from ..config import AppConfig


def _read_env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _read_env_int(name: str, default: int, minimum: int = 1) -> int:
    try:
        value = int(os.getenv(name, ""))
    except ValueError:
        return default
    return max(minimum, value)


def _run_command(command: List[str], *, cwd: Path, timeout: int) -> Dict[str, Any]:
    """Execute *command* capturing stdout/stderr without raising exceptions."""

    print(f"[diagnostics] running command: {' '.join(command)}")
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        return {"ok": False, "error": f"command not found: {exc}"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"timeout after {timeout}s"}
    except Exception as exc:  # pragma: no cover - defensive
        return {"ok": False, "error": str(exc)}

    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()
    return {
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout": stdout,
        "stderr": stderr,
    }


def _collect_git_metadata(repo_root: Path, timeout: int) -> Dict[str, Any]:
    print("[diagnostics] collecting git metadata")
    status = _run_command(["git", "status", "--short", "--branch"], cwd=repo_root, timeout=timeout)
    head = _run_command(["git", "rev-parse", "HEAD"], cwd=repo_root, timeout=timeout)
    describe = _run_command(["git", "describe", "--tags", "--always"], cwd=repo_root, timeout=timeout)

    status_lines = (status.get("stdout") or "").splitlines()
    branch = ""
    if status_lines:
        first = status_lines[0]
        if first.startswith("##"):
            branch = first[2:].strip()

    return {
        "root": str(repo_root),
        "status": status,
        "status_lines": status_lines,
        "head": (head.get("stdout") or "").strip(),
        "describe": (describe.get("stdout") or "").strip(),
        "branch": branch,
        "dirty": any(line.strip() for line in status_lines[1:]),
    }


def _should_run_pytest(include_pytest: bool | None) -> bool:
    if include_pytest is not None:
        return include_pytest
    return _read_env_flag("DIAGNOSTICS_RUN_PYTEST", False)


def _collect_pytest(repo_root: Path, timeout: int, include_pytest: bool | None) -> Dict[str, Any]:
    enabled = _should_run_pytest(include_pytest)
    if not enabled:
        print("[diagnostics] pytest collection skipped (disabled)")
        return {"enabled": False, "result": None}

    print("[diagnostics] running pytest --collect-only")
    args_env = os.getenv("DIAGNOSTICS_PYTEST_ARGS", "").strip()
    extra_args: List[str] = [arg for arg in args_env.split() if arg]
    command = ["pytest", "--collect-only", "-q", *extra_args]
    result = _run_command(command, cwd=repo_root, timeout=timeout)
    return {"enabled": True, "result": result}


def _collect_dependencies(repo_root: Path, timeout: int) -> Dict[str, Any]:
    print("[diagnostics] collecting dependency versions")
    result = _run_command([sys.executable, "-m", "pip", "list", "--format", "json"], cwd=repo_root, timeout=timeout)
    packages: Dict[str, str] = {}
    if result.get("ok") and result.get("stdout"):
        try:
            data = json.loads(result["stdout"])
            if isinstance(data, list):
                for entry in data:
                    if not isinstance(entry, dict):
                        continue
                    name = entry.get("name")
                    version = entry.get("version")
                    if isinstance(name, str) and isinstance(version, str):
                        packages[name] = version
        except json.JSONDecodeError:
            packages = {}
    return {"result": result, "packages": packages}


def _tail_lines(path: Path, limit: int) -> List[str]:
    lines: List[str] = []
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            buffer = handle.readlines()[-limit:]
        lines = [line.rstrip("\n") for line in buffer]
    except FileNotFoundError:
        lines = []
    return lines


def _collect_logs(logs_dir: Path, limit_files: int, limit_lines: int) -> List[Dict[str, Any]]:
    print("[diagnostics] harvesting recent log excerpts")
    if not logs_dir.exists():
        return []
    files = [path for path in logs_dir.glob("*.log") if path.is_file()]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    selected = files[:limit_files]
    payload = []
    for path in selected:
        payload.append(
            {
                "path": str(path),
                "modified": _dt.datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
                "tail": _tail_lines(path, limit_lines),
            }
        )
    return payload


def _render_summary(data: Dict[str, Any]) -> str:
    repo = data.get("repo", {})
    tests = data.get("tests", {})
    deps = data.get("dependencies", {})
    logs = data.get("logs", [])
    generated_at = data.get("generated_at", "")

    summary: List[str] = ["# Diagnostics Report", "", f"Generated at: {generated_at}"]

    head = repo.get("head") or "unknown"
    branch = repo.get("branch") or "n/a"
    describe = repo.get("describe") or ""
    dirty = "yes" if repo.get("dirty") else "no"
    summary.extend(
        [
            "",
            "## Git",
            f"- Branch: {branch}",
            f"- HEAD: {head}",
            f"- Describe: {describe}",
            f"- Dirty: {dirty}",
            "",
            "```",
        ]
    )
    status_lines = repo.get("status_lines") or []
    summary.extend(status_lines or ["(no status output)"])
    summary.extend(["```", ""])

    summary.append("## Pytest Collection")
    if tests.get("enabled"):
        result = tests.get("result") or {}
        summary.append(f"- Return code: {result.get('returncode', 'n/a')}")
        stdout = (result.get("stdout") or "").strip()
        stderr = (result.get("stderr") or "").strip()
        if stdout:
            summary.extend(["", "### Pytest stdout", "```", stdout, "```"])
        if stderr:
            summary.extend(["", "### Pytest stderr", "```", stderr, "```"])
    else:
        summary.append("- Skipped (disabled)")
    summary.append("")

    summary.append("## Dependencies")
    packages = deps.get("packages") or {}
    if packages:
        for name in sorted(packages)[:50]:
            summary.append(f"- {name} {packages[name]}")
        if len(packages) > 50:
            summary.append(f"- ... ({len(packages) - 50} more packages omitted)")
    else:
        result = deps.get("result") or {}
        if result.get("error"):
            summary.append(f"- Error: {result['error']}")
        else:
            summary.append("- No package information available")
    summary.append("")

    summary.append("## Recent Logs")
    if logs:
        for entry in logs:
            summary.extend(
                [
                    "",
                    f"### {entry.get('path')}",
                    f"Modified: {entry.get('modified')}",
                    "```",
                ]
            )
            for line in entry.get("tail", []):
                summary.append(line)
            summary.append("```")
    else:
        summary.append("- No log files were found")

    summary.append("")
    return "\n".join(summary)


def run_diagnostics(config: AppConfig, *, include_pytest: bool | None = None) -> Dict[str, Any]:
    """Gather repository and environment diagnostics for operators."""

    print("[diagnostics] starting diagnostic run")
    repo_root = Path(__file__).resolve().parents[3]
    timestamp = _dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

    timeout = _read_env_int("DIAGNOSTICS_CMD_TIMEOUT", 60)
    log_files = _read_env_int("DIAGNOSTICS_LOG_FILES", 3)
    log_lines = _read_env_int("DIAGNOSTICS_LOG_LINES", 40)

    repo_info = _collect_git_metadata(repo_root, timeout)
    pytest_info = _collect_pytest(repo_root, timeout, include_pytest)
    deps_info = _collect_dependencies(repo_root, timeout)
    logs_info = _collect_logs(config.logs_dir, log_files, log_lines)

    data = {
        "generated_at": timestamp,
        "repo": repo_info,
        "tests": pytest_info,
        "dependencies": deps_info,
        "logs": logs_info,
    }

    summary_markdown = _render_summary(data)
    diagnostics_dir = config.logs_dir / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    summary_path = diagnostics_dir / f"diagnostics-{_dt.datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.md"
    summary_path.write_text(summary_markdown, encoding="utf-8")
    print(f"[diagnostics] summary written to {summary_path}")

    data.update(
        {
            "summary_path": str(summary_path),
            "summary_markdown": summary_markdown,
        }
    )
    print("[diagnostics] completed")
    return data

