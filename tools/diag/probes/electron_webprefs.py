"""Probe Electron BrowserWindow hardening in desktop/electron/src/main.ts."""
from __future__ import annotations

import re
from typing import Iterable, List

from ..engine import Finding, RuleContext, Severity
from . import register_probe

WINDOW_PATTERN = re.compile(r"BrowserWindow\(\s*\{(?P<body>.*?)\}\s*\)", re.DOTALL)
VIEW_PATTERN = re.compile(r"BrowserView\(\s*\{(?P<body>.*?)\}\s*\)", re.DOTALL)


def _extract_block(pattern: re.Pattern[str], text: str) -> str:
    match = pattern.search(text)
    if not match:
        return ""
    return match.group("body")


def _extract_web_preferences(body: str) -> str:
    if not body:
        return ""
    match = re.search(r"webPreferences\s*:\s*\{(?P<web>.*?)\}", body, re.DOTALL)
    if not match:
        return ""
    return match.group("web")


def _line_number(text: str, needle: str) -> int | None:
    index = text.find(needle)
    if index == -1:
        return None
    return text.count("\n", 0, index) + 1


@register_probe(
    "probe_electron_webprefs",
    description="Electron BrowserWindow must enforce hardened webPreferences",
    severity=Severity.HIGH,
)
def probe_electron_web_preferences(context: RuleContext) -> Iterable[Finding]:
    """Ensure desktop BrowserWindow opts into isolation and sandboxing."""

    target = "desktop/electron/src/main.ts"
    text = context.read_text(target)
    if not text:
        return [
            Finding(
                id=f"{target}:missing",
                rule_id="probe_electron_webprefs",
                severity=Severity.HIGH,
                summary="desktop/electron/src/main.ts is missing; cannot verify BrowserWindow settings.",
                suggestion="Restore desktop/electron/src/main.ts so BrowserWindow preferences remain hardened.",
                file=target,
            )
        ]

    findings: List[Finding] = []

    window_block = _extract_block(WINDOW_PATTERN, text)
    webprefs = _extract_web_preferences(window_block)
    if not webprefs:
        findings.append(
            Finding(
                id=f"{target}:webPreferences-missing",
                rule_id="probe_electron_webprefs",
                severity=Severity.HIGH,
                summary="BrowserWindow definition does not include a webPreferences block.",
                suggestion="Provide webPreferences with contextIsolation, nodeIntegration, sandbox, and preload settings.",
                file=target,
                line_hint=_line_number(text, "BrowserWindow"),
            )
        )
    else:
        checks = {
            "contextIsolation: true": "Enable contextIsolation in BrowserWindow webPreferences.",
            "nodeIntegration: false": "Disable nodeIntegration to avoid exposing Node globals to untrusted content.",
            "sandbox: true": "Enable sandboxing in BrowserWindow webPreferences.",
            "preload": "Declare preload script in BrowserWindow webPreferences.",
        }
        for needle, summary in checks.items():
            if needle not in webprefs:
                findings.append(
                    Finding(
                        id=f"{target}:{needle.replace(' ', '-')}",
                        rule_id="probe_electron_webprefs",
                        severity=Severity.HIGH,
                        summary=summary,
                        suggestion="Add the missing setting inside BrowserWindow webPreferences.",
                        file=target,
                        line_hint=_line_number(text, "webPreferences"),
                    )
                )

    view_block = _extract_block(VIEW_PATTERN, text)
    view_webprefs = _extract_web_preferences(view_block)
    if view_block and not view_webprefs:
        findings.append(
            Finding(
                id=f"{target}:BrowserView-webPreferences-missing",
                rule_id="probe_electron_webprefs",
                severity=Severity.MEDIUM,
                summary="BrowserView instantiation is missing hardened webPreferences.",
                suggestion="Provide webPreferences on BrowserView with contextIsolation and sandbox enabled.",
                file=target,
                line_hint=_line_number(text, "BrowserView"),
            )
        )
    elif view_webprefs:
        for needle in ("contextIsolation: true", "sandbox: true"):
            if needle not in view_webprefs:
                findings.append(
                    Finding(
                        id=f"{target}:BrowserView-{needle.replace(' ', '-')}",
                        rule_id="probe_electron_webprefs",
                        severity=Severity.MEDIUM,
                        summary=f"BrowserView webPreferences should include {needle.split(':')[0]}.",
                        suggestion="Update BrowserView webPreferences to keep embedded content isolated.",
                        file=target,
                        line_hint=_line_number(text, "BrowserView"),
                    )
                )

    return findings
