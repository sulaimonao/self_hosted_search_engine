"""Check package.json scripts for required desktop wiring."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, Iterable, List

from .engine import Finding, RuleContext, Severity, register

REQUIRED_SCRIPTS = (
    "dev:desktop",
    "dev:web",
    "dev:api",
    "dev:electron:wait",
    "build:desktop",
    "build:web",
)
PORT_RE = re.compile(r"localhost:(\d+)")
API_PORT_RE = re.compile(r"BACKEND_PORT=(\d+)")
EXPECTED_WEB_PORT = "3100"
EXPECTED_API_PORT = "5050"


def _load_package_json(root: Path, relative: str) -> Dict[str, str]:
    package_path = root / relative
    if not package_path.exists():
        return {}
    try:
        payload = json.loads(package_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    scripts = payload.get("scripts") or {}
    if not isinstance(scripts, dict):
        return {}
    return {key: str(value) for key, value in scripts.items()}


@register(
    "R11",
    description="Ensure dev/build scripts expose consistent ports",
    severity=Severity.MEDIUM,
)
def rule_ports_and_scripts(context: RuleContext) -> Iterable[Finding]:
    findings: List[Finding] = []
    root = context.root
    script_sets = {
        "package.json": _load_package_json(root, "package.json"),
        "frontend/package.json": _load_package_json(root, "frontend/package.json"),
    }

    missing_scripts: List[str] = []
    for name, scripts in script_sets.items():
        for required in REQUIRED_SCRIPTS:
            if required not in scripts:
                missing_scripts.append(f"{name}:{required}")
    if missing_scripts:
        findings.append(
            Finding(
                id="scripts:missing",
                rule_id="R11",
                severity=Severity.MEDIUM,
                summary=f"Missing required desktop scripts: {', '.join(sorted(missing_scripts))}.",
                suggestion="Add npm scripts for dev:desktop/dev:web/dev:api/dev:electron:wait/build:desktop/build:web.",
            )
        )

    # Port consistency check
    ports = set()
    api_ports = set()
    for scripts in script_sets.values():
        for command in scripts.values():
            ports.update(PORT_RE.findall(command))
            api_ports.update(API_PORT_RE.findall(command))
    ports.discard(EXPECTED_WEB_PORT)
    api_ports.discard(EXPECTED_API_PORT)
    if ports:
        findings.append(
            Finding(
                id="scripts:port-mismatch",
                rule_id="R11",
                severity=Severity.LOW,
                summary=f"Detected dev scripts binding unexpected web ports: {', '.join(sorted(ports))}.",
                suggestion=f"Normalise desktop dev web ports to {EXPECTED_WEB_PORT} (update scripts or environment overrides).",
            )
        )
    if api_ports:
        findings.append(
            Finding(
                id="scripts:api-port-mismatch",
                rule_id="R11",
                severity=Severity.LOW,
                summary=f"Detected BACKEND_PORT values that differ from {EXPECTED_API_PORT}: {', '.join(sorted(api_ports))}.",
                suggestion=f"Align backend dev scripts with BACKEND_PORT={EXPECTED_API_PORT} so renderer rewrites stay in sync.",
            )
        )

    return findings
