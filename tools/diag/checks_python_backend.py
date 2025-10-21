"""Python backend health diagnostics."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Iterable, List, Set

import tomllib

from .engine import Finding, RuleContext, Severity, register

REQ_RE = re.compile(r"^([A-Za-z0-9_.-]+)")
PINNED_RE = re.compile(r"(==|~=|>=)")
DEBUG_RE = re.compile(r"debug\s*=\s*True")
FLASK_ENV_RE = re.compile(r"FLASK_ENV=development|FLASK_DEBUG=1")

CRITICAL_LIBS = {"flask", "fastapi", "uvicorn", "gunicorn", "hypercorn", "quart"}


def _parse_requirements(path: Path) -> Dict[str, str]:
    packages: Dict[str, str] = {}
    if not path.exists():
        return packages
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = REQ_RE.match(line)
        if not match:
            continue
        name = match.group(1).lower()
        packages[name] = line
    return packages


def _parse_pyproject(path: Path) -> Set[str]:
    if not path.exists():
        return set()
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    deps: Set[str] = set()
    project = data.get("project", {})
    dependencies = project.get("dependencies", [])
    for dep in dependencies:
        if isinstance(dep, str):
            match = REQ_RE.match(dep)
            if match:
                deps.add(match.group(1).lower())
    optional = project.get("optional-dependencies", {})
    if isinstance(optional, dict):
        for group in optional.values():
            for dep in group or []:
                if isinstance(dep, str):
                    match = REQ_RE.match(dep)
                    if match:
                        deps.add(match.group(1).lower())
    return deps


@register(
    "R13",
    description="Python backend dependencies must be pinned and aligned",
    severity=Severity.MEDIUM,
)
def rule_python_backend(context: RuleContext) -> Iterable[Finding]:
    findings: List[Finding] = []
    requirements = _parse_requirements(context.root / "requirements.txt")
    pyproject_deps = _parse_pyproject(context.root / "pyproject.toml")

    # Detect packages missing from pyproject.
    missing = sorted(name for name in requirements if name not in pyproject_deps)
    if missing:
        findings.append(
            Finding(
                id="python:pyproject-mismatch",
                rule_id="R13",
                severity=Severity.MEDIUM,
                summary=f"requirements.txt contains packages missing from pyproject.toml: {', '.join(missing)}.",
                suggestion="Mirror runtime dependencies in pyproject.toml so editable installs stay in sync.",
            )
        )

    # Detect unpinned critical libraries.
    for name, line in requirements.items():
        if name in CRITICAL_LIBS and not PINNED_RE.search(line):
            findings.append(
                Finding(
                    id=f"python:unpinned:{name}",
                    rule_id="R13",
                    severity=Severity.HIGH,
                    summary=f"Critical backend library '{name}' is not pinned in requirements.txt.",
                    suggestion="Pin critical web server dependencies using == or ~= to avoid runtime regressions.",
                    evidence=line,
                )
            )

    # Search for Flask debug toggles.
    for relative in context.iter_patterns("backend/**/*.py", "scripts/**/*.sh", "scripts/**/*.py"):
        text = context.read_text(relative)
        debug_match = DEBUG_RE.search(text)
        env_match = FLASK_ENV_RE.search(text)
        if debug_match or env_match:
            match = debug_match or env_match
            line_no = text.count("\n", 0, match.start()) + 1
            findings.append(
                Finding(
                    id=f"python:debug:{relative}:{line_no}",
                    rule_id="R13",
                    severity=Severity.MEDIUM,
                    summary="Flask debug mode detected in repository scripts.",
                    suggestion="Remove debug=True and FLASK_ENV=development from committed scripts; gate them behind env vars.",
                    file=relative,
                    line_hint=line_no,
                )
            )
    return findings
