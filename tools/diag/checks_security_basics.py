"""Security baseline diagnostics."""
from __future__ import annotations

import re
from typing import Iterable, List, Set

from .engine import Finding, RuleContext, Severity, register

ENV_CALL_RE = re.compile(r"(?:os\.(?:environ\[['\"]|getenv\(['\"])|process\.env\.)([A-Z0-9_]+)")
ENV_ASSIGN_RE = re.compile(r"^\s*([A-Z0-9_]+)\s*=", re.MULTILINE)
IGNORED_ENV = {"NODE_ENV", "PORT", "PYTHONPATH", "PATH", "HOME", "DEBUG"}

UNSAFE_PREFS = (
    ("worldSafeExecuteJavaScript", "false", "R15"),
    ("enableRemoteModule", "true", "R15"),
    ("sandbox", "false", "R16"),
)


@register(
    "R14",
    description="Document environment variables in .env.example",
    severity=Severity.MEDIUM,
)
def rule_env_examples(context: RuleContext) -> Iterable[Finding]:
    findings: List[Finding] = []
    referenced: Set[str] = set()
    for relative in context.iter_patterns("**/*.py", "**/*.ts", "**/*.tsx", "**/*.js"):
        text = context.read_text(relative)
        for match in ENV_CALL_RE.finditer(text):
            key = match.group(1)
            if key not in IGNORED_ENV:
                referenced.add(key)
    example_keys: Set[str] = set()
    for relative in context.iter_patterns("*.env.example", "**/.env.example", "**/.env" ):
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
                summary=f"Environment keys referenced in code lack .env.example entries: {', '.join(missing)}.",
                suggestion="Add the missing keys to .env.example with safe defaults or documentation.",
            )
        )
    return findings


@register(
    "R15",
    description="Avoid dangerous Electron preference flags",
    severity=Severity.HIGH,
)
def rule_electron_prefs(context: RuleContext) -> Iterable[Finding]:
    findings: List[Finding] = []
    for relative in context.iter_patterns("electron/**/*.js", "electron/**/*.ts", "desktop/**/*.ts"):
        text = context.read_text(relative)
        for key, bad_value, rule_id in UNSAFE_PREFS[:2]:
            needle = f"{key}: {bad_value}"
            pos = text.find(needle)
            if pos == -1:
                continue
            line_no = text.count("\n", 0, pos) + 1
            findings.append(
                Finding(
                    id=f"{relative}:{key}:{line_no}",
                    rule_id="R15",
                    severity=Severity.HIGH,
                    summary=f"webPreferences.{key}={bad_value} weakens Electron isolation.",
                    suggestion="Remove worldSafeExecuteJavaScript/enableRemoteModule overrides; rely on contextBridge APIs instead.",
                    file=relative,
                    line_hint=line_no,
                )
            )
    return findings


@register(
    "R16",
    description="Keep sandbox and CSP safeguards enabled",
    severity=Severity.HIGH,
)
def rule_sandbox_disabled(context: RuleContext) -> Iterable[Finding]:
    findings: List[Finding] = []
    for relative in context.iter_patterns("electron/**/*.js", "electron/**/*.ts", "desktop/**/*.ts", "frontend/**/*.ts"):
        text = context.read_text(relative)
        needle = "sandbox: false"
        pos = text.find(needle)
        if pos != -1:
            line_no = text.count("\n", 0, pos) + 1
            findings.append(
                Finding(
                    id=f"{relative}:sandbox:{line_no}",
                    rule_id="R16",
                    severity=Severity.HIGH,
                    summary="webPreferences.sandbox disabled; preload scripts run in unsafe world.",
                    suggestion="Enable sandbox true and ensure preload uses contextBridge for vetted APIs.",
                    file=relative,
                    line_hint=line_no,
                )
            )
    return findings
