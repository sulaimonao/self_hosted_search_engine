"""Ensure environment keys referenced in code are documented."""
from __future__ import annotations

import re
from typing import Iterable, List, Set

from ..engine import Finding, RuleContext, Severity, register

ENV_CALL_RE = re.compile(
    r"(?:os\.(?:environ\[['\"]|getenv\(['\"])|process\.env\.)([A-Z0-9_]+)"
)
ENV_ASSIGN_RE = re.compile(r"^\s*([A-Z0-9_]+)\s*=", re.MULTILINE)
IGNORED_ENV = {"NODE_ENV", "PORT", "PYTHONPATH", "PATH", "HOME", "DEBUG"}
ENV_EXAMPLE_PATTERNS = ("*.env.example", "**/.env.example", "**/.env")
SOURCE_PATTERNS = ("**/*.py", "**/*.ts", "**/*.tsx", "**/*.js")


@register(
    "R14",
    description="Document environment variables in .env.example",
    severity=Severity.MEDIUM,
)
def rule_env_examples(context: RuleContext) -> Iterable[Finding]:
    findings: List[Finding] = []
    referenced: Set[str] = set()
    for relative in context.iter_patterns(*SOURCE_PATTERNS):
        text = context.read_text(relative)
        for match in ENV_CALL_RE.finditer(text):
            key = match.group(1)
            if key not in IGNORED_ENV:
                referenced.add(key)
    example_keys: Set[str] = set()
    for relative in context.iter_patterns(*ENV_EXAMPLE_PATTERNS):
        text = context.read_text(relative)
        for key in ENV_ASSIGN_RE.findall(text):
            example_keys.add(key)
    missing = sorted(key for key in referenced if key not in example_keys)
    if missing:
        findings.append(
            Finding(
                id="env:missing-example",
                rule_id="R14",
                severity=Severity.MEDIUM,
                summary=(
                    "Environment keys referenced in code lack .env.example entries: "
                    + ", ".join(missing)
                    + "."
                ),
                suggestion="Add the missing keys to .env.example with safe defaults or documentation.",
            )
        )
    return findings
