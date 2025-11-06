"""Check dependency drift between pyproject.toml and requirements.txt."""
from __future__ import annotations

import re
from typing import Iterable, List, Set

try:  # Python 3.11+
    import tomllib  # type: ignore
except ModuleNotFoundError:  # Python <3.11 fallback
    import tomli as tomllib  # type: ignore

from ..engine import Finding, RuleContext, Severity, register

_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+")


def _normalise(name: str) -> str:
    return name.replace("_", "-").lower()


def _extract_name(spec: str) -> str | None:
    match = _NAME_RE.match(spec.strip())
    if not match:
        return None
    return _normalise(match.group(0))


def _collect_requirements(text: str) -> Set[str]:
    names: Set[str] = set()
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        name = _extract_name(line)
        if name:
            names.add(name)
    return names


def _collect_pyproject(context: RuleContext) -> Set[str]:
    text = context.read_text("pyproject.toml")
    if not text.strip():
        return set()
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return set()

    names: Set[str] = set()

    project = data.get("project")
    if isinstance(project, dict):
        deps = project.get("dependencies")
        if isinstance(deps, list):
            for dep in deps:
                if isinstance(dep, str):
                    name = _extract_name(dep)
                    if name:
                        names.add(name)
        opt = project.get("optional-dependencies")
        if isinstance(opt, dict):
            for items in opt.values():
                if isinstance(items, list):
                    for dep in items:
                        if isinstance(dep, str):
                            name = _extract_name(dep)
                            if name:
                                names.add(name)

    tool = data.get("tool")
    if isinstance(tool, dict):
        poetry = tool.get("poetry")
        if isinstance(poetry, dict):
            for section in ("dependencies", "dev-dependencies"):
                deps = poetry.get(section)
                if isinstance(deps, dict):
                    for key in deps:
                        name = _extract_name(str(key))
                        if name:
                            names.add(name)

    return names


@register(
    "R21_dependency_sync",
    description="Align dependencies between requirements.txt and pyproject.toml",
    severity=Severity.MEDIUM,
)
def rule_dependency_sync(context: RuleContext) -> Iterable[Finding]:
    requirements_text = context.read_text("requirements.txt")
    if not requirements_text.strip():
        return []

    pyproject_names = _collect_pyproject(context)
    if not pyproject_names:
        return []

    requirements_names = _collect_requirements(requirements_text)

    findings: List[Finding] = []

    missing_in_pyproject = sorted(requirements_names - pyproject_names)
    if missing_in_pyproject:
        findings.append(
            Finding(
                id="deps:requirements-only",
                rule_id="R21_dependency_sync",
                severity=Severity.LOW,
                summary=(
                    "requirements.txt lists packages absent from pyproject.toml: "
                    + ", ".join(missing_in_pyproject)
                    + "."
                ),
                suggestion="Declare these dependencies in pyproject.toml or remove them from requirements.txt.",
                file="requirements.txt",
            )
        )

    missing_in_requirements = sorted(pyproject_names - requirements_names)
    if missing_in_requirements:
        findings.append(
            Finding(
                id="deps:pyproject-only",
                rule_id="R21_dependency_sync",
                severity=Severity.MEDIUM,
                summary=(
                    "pyproject.toml declares packages missing from requirements.txt: "
                    + ", ".join(missing_in_requirements)
                    + "."
                ),
                suggestion="Synchronise requirements.txt with pyproject.toml to keep dependency installs aligned.",
                file="pyproject.toml",
            )
        )

    return findings
