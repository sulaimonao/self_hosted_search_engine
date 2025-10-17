"""Repository maintenance tools exposed to the autonomous agent.

The functions in this module provide a curated surface area for reading and
writing to the repository without offering arbitrary shell access. Every
write-aware function enforces an allowlist/denylist policy and small change
budgets so the agent can only land safe, well-scoped diffs.

The default policy is intentionally conservative; at runtime the hosting
application can call :func:`load_policy` to override the limits with the
contents of ``policy/allowlist.yml``.
"""

from __future__ import annotations

import json
import os
import subprocess  # nosec B404
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple, cast
import sys

import yaml  # type: ignore[import]

from server.tool_logging import log_tool


@dataclass
class Policy:
    """Allowlist configuration for repository mutations."""

    write_paths: Sequence[str]
    deny_paths: Sequence[str]
    max_changed_files: int
    max_changed_loc: int

    def is_path_allowed(self, path: str) -> bool:
        candidate = _normalize_candidate_path(path)
        if not candidate:
            return False

        for deny in self.deny_paths:
            prefix = _normalize_policy_prefix(deny)
            if prefix == "*":
                return False
            if prefix and _matches_prefix(candidate, prefix):
                return False

        for allow in self.write_paths:
            if allow.strip() == "*":
                return True
            prefix = _normalize_policy_prefix(allow)
            if prefix and _matches_prefix(candidate, prefix):
                return True

        return False


DEFAULT_POLICY = Policy(
    write_paths=("backend/", "server/", "bin/", "tests/"),
    deny_paths=(".env", "data/", ".github/"),
    max_changed_files=10,
    max_changed_loc=500,
)

_policy: Policy = DEFAULT_POLICY


def _normalize_candidate_path(path: str) -> str:
    """Return a normalized, safe repository path or ``""`` when invalid."""

    raw = str(path).strip().replace("\\", "/")
    if not raw:
        return ""
    while raw.startswith("./"):
        raw = raw[2:]
    if not raw or raw.startswith("../") or raw.startswith("/"):
        return ""
    normalized = PurePosixPath(raw)
    if any(part == ".." for part in normalized.parts):
        return ""
    text = str(normalized)
    return "" if text == "." else text


def _normalize_policy_prefix(path: str) -> str:
    """Normalize policy prefixes, handling wildcards and directory suffixes."""

    raw = str(path).strip().replace("\\", "/")
    if not raw:
        return ""
    if raw == "*":
        return "*"
    while raw.startswith("./"):
        raw = raw[2:]
    if raw.endswith("/**"):
        raw = raw[:-3]
    if raw.endswith("/*"):
        raw = raw[:-2]
    raw = raw.rstrip("/")
    if not raw or raw.startswith("../") or raw.startswith("/"):
        return ""
    normalized = PurePosixPath(raw)
    if any(part == ".." for part in normalized.parts):
        return ""
    text = str(normalized)
    return "" if text == "." else text


def _matches_prefix(candidate: str, prefix: str) -> bool:
    if prefix == "*":
        return True
    if candidate == prefix:
        return True
    return candidate.startswith(f"{prefix}/")


def _coerce_sequence(value: object, default: Sequence[str]) -> Tuple[str, ...]:
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value)
    if isinstance(value, str):
        return (value,)
    return tuple(default)


def load_policy(path: str | os.PathLike[str]) -> None:
    """Load policy configuration from ``policy/allowlist.yml``."""

    global _policy
    policy_path = Path(path)
    if not policy_path.exists():
        _policy = DEFAULT_POLICY
        return
    with policy_path.open("r", encoding="utf-8") as handle:
        raw_payload = yaml.safe_load(handle) or {}
    if not isinstance(raw_payload, Mapping):
        raise ValueError("policy/allowlist.yml must define a mapping")
    payload = cast(Mapping[str, Any], raw_payload)
    write_paths = _coerce_sequence(
        payload.get("write_paths"), DEFAULT_POLICY.write_paths
    )
    deny_paths = _coerce_sequence(payload.get("deny_paths"), DEFAULT_POLICY.deny_paths)
    raw_limits = payload.get("limits", {})
    limits = (
        cast(Mapping[str, Any], raw_limits) if isinstance(raw_limits, Mapping) else {}
    )
    max_changed_files = int(
        cast(Any, limits.get("max_changed_files", DEFAULT_POLICY.max_changed_files))
    )
    max_changed_loc = int(
        cast(Any, limits.get("max_changed_loc", DEFAULT_POLICY.max_changed_loc))
    )
    _policy = Policy(write_paths, deny_paths, max_changed_files, max_changed_loc)


def _ensure_safe_path(path: str) -> None:
    if not _policy.is_path_allowed(path):
        raise RuntimeError(f"path not allowed: {path}")


def repo_tree(path: str = ".", depth: int = 2) -> List[str]:
    """Return tracked files up to ``depth`` levels deep."""

    try:
        out = _check_output(["git", "ls-files", path])
    except subprocess.CalledProcessError as exc:  # pragma: no cover - relies on git
        raise RuntimeError("git ls-files failed") from exc
    return [p for p in out.splitlines() if p.count("/") <= depth]


def code_search(query: str, *, max_results: int | None = None) -> List[str]:
    """Search tracked files using ripgrep, returning ``path:line:col:snippet``."""

    cmd = ["rg", "-n", "--no-heading", query]
    if max_results:
        cmd.extend(["-m", str(max_results)])
    try:
        out = _check_output(cmd)
    except subprocess.CalledProcessError:
        return []  # No matches (rg exits 1) or rg missing.
    return [line for line in out.splitlines() if line.strip()]


def repo_read(path: str, start: int = 1, end: int = 400) -> str:
    """Read a slice of a file (1-indexed inclusive)."""

    if start < 1 or end < start:
        raise ValueError("invalid range")
    target = Path(path)
    if not target.exists():
        return ""
    with target.open("r", encoding="utf-8", errors="ignore") as handle:
        lines = handle.readlines()[start - 1 : end]
    return "".join(lines)


def _budget_guard(diff: str) -> None:
    files: set[str] = set()
    loc = 0
    for line in diff.splitlines():
        if line.startswith("+++ b/") or line.startswith("--- a/"):
            _, _, rest = line.partition(" ")
            candidate = rest.strip().lstrip("ab/")
            if candidate and candidate != "/dev/null":
                files.add(candidate)
        elif line.startswith("+") or line.startswith("-"):
            if not (line.startswith("+++") or line.startswith("---")):
                loc += 1
    if len(files) > _policy.max_changed_files or loc > _policy.max_changed_loc:
        raise RuntimeError(f"change budget exceeded: files={len(files)} loc={loc}")


@log_tool("repo.write_unified_diff")
def repo_write_unified_diff(diff: str) -> Dict[str, object]:
    """Apply a unified diff via ``git apply --index`` within policy bounds."""

    _budget_guard(diff)
    for line in diff.splitlines():
        if line.startswith("+++ b/") or line.startswith("--- a/"):
            _, _, rest = line.partition(" ")
            candidate = rest.strip().lstrip("ab/")
            if candidate and candidate != "/dev/null":
                _ensure_safe_path(candidate)

    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as temp:
        temp.write(diff)
        temp_path = temp.name
    try:
        _check_call(["git", "apply", "--index", temp_path])
    except subprocess.CalledProcessError as exc:  # pragma: no cover - delegates to git
        raise RuntimeError("git apply failed") from exc
    finally:
        Path(temp_path).unlink(missing_ok=True)
    return {"applied": True}


def _run_command(cmd: Sequence[str]) -> Dict[str, object]:
    try:
        completed = subprocess.run(
            cmd, text=True, capture_output=True, check=False
        )  # nosec B603
    except FileNotFoundError:  # pragma: no cover - depends on runtime env
        return {"ok": False, "out": f"command not found: {cmd[0]}", "returncode": 127}
    return {
        "ok": completed.returncode == 0,
        "out": completed.stdout + completed.stderr,
        "returncode": completed.returncode,
    }


def _repo_diag_command(args: Sequence[str]) -> Dict[str, object]:
    """Invoke the repo diagnostics CLI and coerce the JSON payload."""

    cmd = [sys.executable, "-m", "tools.diag.tool", *[str(part) for part in args]]
    try:
        completed = subprocess.run(
            cmd, text=True, capture_output=True, check=False  # nosec B603
        )
    except FileNotFoundError as exc:  # pragma: no cover - depends on interpreter availability
        return {"ok": False, "error": str(exc), "command": cmd}
    stdout = (completed.stdout or "").strip()
    payload: Dict[str, Any]
    if stdout:
        try:
            parsed = json.loads(stdout)
        except json.JSONDecodeError:
            payload = {"output": stdout}
        else:
            payload = parsed if isinstance(parsed, dict) else {"output": parsed}
    else:
        payload = {}
    if completed.stderr:
        payload["stderr"] = (completed.stderr or "").strip()
    payload.setdefault("exit_code", completed.returncode)
    payload["returncode"] = completed.returncode
    payload["ok"] = payload.get("exit_code", completed.returncode) == 0
    payload["command"] = cmd
    return payload


@log_tool("repo_diag.list")
def repo_diag_list_probes() -> Dict[str, object]:
    """Return the expanded diagnostics manifest."""

    return _repo_diag_command(["list"])


@log_tool("repo_diag.run")
def repo_diag_run(labels: Iterable[str] | None = None) -> Dict[str, object]:
    """Run diagnostics (optionally limited to specific probe labels)."""

    args: List[str] = ["run"]
    if labels:
        args.append("--labels")
        args.extend(str(label) for label in labels)
    return _repo_diag_command(args)


@log_tool("repo_diag.artifacts")
def repo_diag_artifacts() -> Dict[str, object]:
    """Return paths to the latest diagnostics artifacts."""

    return _repo_diag_command(["artifacts"])


@log_tool("repo_diag.start")
def repo_diag_start_services() -> Dict[str, object]:
    """Ensure diagnostics services are running (idempotent)."""

    return _repo_diag_command(["start"])


@log_tool("repo_diag.stop")
def repo_diag_stop_services() -> Dict[str, object]:
    """Stop diagnostics services (no-op; included for symmetry)."""

    return _repo_diag_command(["stop"])


REPO_DIAG_TOOL_SCHEMA: Dict[str, Any] = {
    "name": "repo_diag",
    "description": "Diagnose the repo: bring up services, list probes, run probes, and fetch artifacts.",
    "functions": [
        {
            "name": "list_probes",
            "description": "Return the auto-expanded probe manifest",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "run",
            "description": "Run diagnostics (optionally only some probes).",
            "parameters": {
                "type": "object",
                "properties": {"labels": {"type": "array", "items": {"type": "string"}}},
                "required": [],
                "additionalProperties": False,
            },
        },
        {
            "name": "artifacts",
            "description": "Get latest run artifact paths",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "start_services",
            "description": "Ensure API and renderer are up (reused if already running)",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "stop_services",
            "description": "No-op (spawned processes auto-terminate on exit)",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    ],
}


def _check_output(cmd: Sequence[str]) -> str:
    return subprocess.check_output(list(cmd), text=True)  # nosec


def _check_call(cmd: Sequence[str]) -> None:
    subprocess.check_call(list(cmd))  # nosec


def run_linters() -> Dict[str, object]:
    steps = {
        "ruff": ["ruff", "check", "server", "scripts", "policy"],
        "black": [
            "black",
            "--check",
            "server/agent_tools_repo.py",
            "server/agent_policy.py",
            "scripts/change_budget.py",
            "scripts/perf_smoke.py",
            "tests/e2e/test_agent_patch_flow.py",
        ],
        "mypy": [
            "mypy",
            "--ignore-missing-imports",
            "server/agent_tools_repo.py",
            "server/agent_policy.py",
            "scripts/change_budget.py",
            "scripts/perf_smoke.py",
        ],
    }
    results: Dict[str, object] = {}
    overall = True
    for name, cmd in steps.items():
        outcome = _run_command(cmd)
        results[name] = outcome
        overall = overall and bool(outcome.get("ok"))
    results["ok"] = overall
    return results


def run_tests(selectors: Iterable[str] | None = None) -> Dict[str, object]:
    cmd = ["pytest", "-q"]
    if selectors:
        cmd.extend(selectors)
    return _run_command(cmd)


def run_security_scan() -> Dict[str, object]:
    steps = {
        "pip-audit": ["pip-audit", "-r", "requirements.txt"],
        "bandit": [
            "bandit",
            "-q",
            "server/agent_tools_repo.py",
            "scripts/change_budget.py",
            "scripts/perf_smoke.py",
        ],
    }
    results: Dict[str, object] = {}
    overall = True
    for name, cmd in steps.items():
        outcome = _run_command(cmd)
        results[name] = outcome
        overall = overall and bool(outcome.get("ok"))
    results["ok"] = overall
    return results


def run_perf_smoke() -> Dict[str, object]:
    return _run_command(["python", "scripts/perf_smoke.py"])


def git_branch(name: str) -> None:
    try:
        _check_call(["git", "checkout", "-B", name])
    except subprocess.CalledProcessError as exc:  # pragma: no cover
        raise RuntimeError("git checkout failed") from exc


def git_diff() -> str:
    try:
        return _check_output(["git", "diff", "--cached"])
    except subprocess.CalledProcessError as exc:  # pragma: no cover
        raise RuntimeError("git diff failed") from exc


def git_commit(message: str) -> None:
    try:
        _check_call(["git", "commit", "-m", message])
    except subprocess.CalledProcessError as exc:  # pragma: no cover
        raise RuntimeError("git commit failed") from exc


def open_pr(title: str, body: str) -> Dict[str, object]:
    cmd = [
        "gh",
        "pr",
        "create",
        "--fill",
        "--title",
        title,
        "--body",
        body,
    ]
    outcome = _run_command(cmd)
    outcome.setdefault("out", "")
    return outcome


# Load policy on import so defaults can be overridden by configuration.
load_policy(Path(__file__).resolve().parent.parent / "policy" / "allowlist.yml")
