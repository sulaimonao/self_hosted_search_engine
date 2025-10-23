"""Security baseline diagnostics."""
from __future__ import annotations

from typing import Iterable, List

from .engine import Finding, RuleContext, Severity, register

UNSAFE_PREFS = (
    ("worldSafeExecuteJavaScript", "false", "R15"),
    ("enableRemoteModule", "true", "R15"),
    ("sandbox", "false", "R16"),
)


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
