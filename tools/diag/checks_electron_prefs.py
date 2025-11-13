"""Electron BrowserWindow preference checks."""

from __future__ import annotations

import re
from typing import Iterable, List, Tuple

from .engine import Finding, RuleContext, Severity, register

BROWSER_PATTERNS = (
    "electron/**/*.js",
    "electron/**/*.ts",
    "electron/**/*.tsx",
    "electron/**/*.mjs",
    "electron/**/*.cjs",
    "electron/*.js",
    "electron/*.ts",
    "electron/*.tsx",
    "electron/*.mjs",
    "electron/*.cjs",
    "desktop/**/*.ts",
    "desktop/**/*.js",
    "desktop/*.ts",
    "desktop/*.js",
)

USER_AGENT_RE = re.compile(r"DESKTOP_USER_AGENT\s*=\s*['\"]([^'\"]+)['\"]")


def _find_block(text: str, start_index: int) -> Tuple[int, int]:
    depth = 0
    for index in range(start_index, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return start_index, index + 1
    return start_index, start_index


def _iter_web_preferences(text: str) -> Iterable[Tuple[int, str]]:
    needle = "webPreferences"
    index = 0
    while True:
        pos = text.find(needle, index)
        if pos == -1:
            break
        brace_pos = text.find("{", pos)
        if brace_pos == -1:
            break
        start, end = _find_block(text, brace_pos)
        if end == start:
            break
        yield pos, text[start:end]
        index = end


@register(
    "R4",
    description="Electron BrowserWindow must enable webviewTag",
    severity=Severity.HIGH,
)
def rule_webview_tag(context: RuleContext) -> Iterable[Finding]:
    findings: List[Finding] = []
    for relative in context.iter_patterns(*BROWSER_PATTERNS):
        text = context.read_text(relative)
        for pos, block in _iter_web_preferences(text):
            if "webviewTag" not in block:
                line_no = text.count("\n", 0, pos) + 1
                findings.append(
                    Finding(
                        id=f"{relative}:webviewTag:{line_no}",
                        rule_id="R4",
                        severity=Severity.HIGH,
                        summary="BrowserWindow webPreferences missing webviewTag: true.",
                        suggestion="Set webPreferences.webviewTag = true to allow controlled embedded browsing.",
                        file=relative,
                        line_hint=line_no,
                    )
                )
            elif (
                "webviewTag" in block
                and "true" not in block.split("webviewTag", 1)[1].split(",", 1)[0]
            ):
                line_no = text.count("\n", 0, pos) + 1
                findings.append(
                    Finding(
                        id=f"{relative}:webviewTagFalse:{line_no}",
                        rule_id="R4",
                        severity=Severity.HIGH,
                        summary="webviewTag is configured but not set to true.",
                        suggestion="Enable webPreferences.webviewTag so the desktop shell can host trusted content.",
                        file=relative,
                        line_hint=line_no,
                    )
                )
    return findings


@register(
    "R5",
    description="Electron webview partition must persist",
    severity=Severity.MEDIUM,
)
def rule_partition_persist(context: RuleContext) -> Iterable[Finding]:
    findings: List[Finding] = []
    for relative in context.iter_patterns(*BROWSER_PATTERNS):
        text = context.read_text(relative)
        for pos, block in _iter_web_preferences(text):
            if "partition" not in block:
                line_no = text.count("\n", 0, pos) + 1
                findings.append(
                    Finding(
                        id=f"{relative}:partition-missing:{line_no}",
                        rule_id="R5",
                        severity=Severity.MEDIUM,
                        summary="webPreferences missing partition for persistent storage.",
                        suggestion="Set webPreferences.partition = 'persist:main' to share cookies and storage.",
                        file=relative,
                        line_hint=line_no,
                    )
                )
                continue
            partition_segment = block.split("partition", 1)[1]
            if "persist:" not in partition_segment.split(",", 1)[0]:
                line_no = text.count("\n", 0, pos) + 1
                findings.append(
                    Finding(
                        id=f"{relative}:partition-volatile:{line_no}",
                        rule_id="R5",
                        severity=Severity.MEDIUM,
                        summary="webPreferences.partition should be persist:* for durable sessions.",
                        suggestion="Use a persist:* partition (e.g. 'persist:main') instead of a transient partition.",
                        file=relative,
                        line_hint=line_no,
                        evidence=partition_segment.split(",", 1)[0].strip(),
                    )
                )
    return findings


@register(
    "R6",
    description="Avoid nodeIntegration without contextIsolation",
    severity=Severity.HIGH,
)
def rule_node_integration(context: RuleContext) -> Iterable[Finding]:
    findings: List[Finding] = []
    for relative in context.iter_patterns(*BROWSER_PATTERNS):
        text = context.read_text(relative)
        for pos, block in _iter_web_preferences(text):
            node_enabled = (
                "nodeIntegration" in block
                and "true" in block.split("nodeIntegration", 1)[1].split(",", 1)[0]
            )
            isolation_disabled = (
                "contextIsolation" in block
                and "false" in block.split("contextIsolation", 1)[1].split(",", 1)[0]
            )
            if node_enabled and isolation_disabled:
                line_no = text.count("\n", 0, pos) + 1
                findings.append(
                    Finding(
                        id=f"{relative}:nodeIntegration:{line_no}",
                        rule_id="R6",
                        severity=Severity.HIGH,
                        summary="nodeIntegration:true with contextIsolation:false exposes preload globals to untrusted content.",
                        suggestion="Keep contextIsolation true (or disable nodeIntegration) and move IPC bridges to preload.",
                        file=relative,
                        line_hint=line_no,
                    )
                )
    return findings


@register(
    "R7",
    description="Prefer hardware acceleration for smoother browsing",
    severity=Severity.MEDIUM,
)
def rule_disable_hardware(context: RuleContext) -> Iterable[Finding]:
    findings: List[Finding] = []
    for relative in context.iter_patterns(*BROWSER_PATTERNS):
        text = context.read_text(relative)
        needle = "disableHardwareAcceleration"
        pos = text.find(needle)
        if pos == -1:
            continue
        line_no = text.count("\n", 0, pos) + 1
        findings.append(
            Finding(
                id=f"{relative}:disableHardware:{line_no}",
                rule_id="R7",
                severity=Severity.MEDIUM,
                summary="app.disableHardwareAcceleration() reduces rendering fidelity for browser surfaces.",
                suggestion="Remove disableHardwareAcceleration unless a documented GPU bug requires it and add notes if so.",
                file=relative,
                line_hint=line_no,
            )
        )
    return findings


@register(
    "R26_robot_captcha_risk",
    description="Desktop browser session should spoof UA and locale headers to avoid bot detection",
    severity=Severity.MEDIUM,
)
def rule_robot_captcha_risk(context: RuleContext) -> Iterable[Finding]:
    findings: List[Finding] = []
    targets = (
        "desktop/main.ts",
        "desktop/main.js",
        "desktop/**/main.ts",
        "desktop/**/main.js",
        "electron/main.js",
    )
    for relative in context.iter_patterns(*targets):
        text = context.read_text(relative)
        if not text:
            continue
        match = USER_AGENT_RE.search(text)
        if not match:
            findings.append(
                Finding(
                    id=f"{relative}:ua-missing",
                    rule_id="R26_robot_captcha_risk",
                    severity=Severity.MEDIUM,
                    summary="Desktop main process does not override the renderer user agent.",
                    suggestion="Define DESKTOP_USER_AGENT with a stable Chrome UA before issuing navigation requests.",
                    file=relative,
                )
            )
        else:
            ua = match.group(1)
            lowered = ua.lower()
            if "headless" in lowered or "electron" in lowered or "puppeteer" in lowered:
                findings.append(
                    Finding(
                        id=f"{relative}:ua-robotic",
                        rule_id="R26_robot_captcha_risk",
                        severity=Severity.MEDIUM,
                        summary="Configured desktop user agent contains headless or electron identifiers that trigger captchas.",
                        suggestion="Use a mainstream Chrome/Safari UA string without Headless/Electron tokens.",
                        file=relative,
                        evidence=ua,
                    )
                )
        if "Accept-Language" not in text:
            findings.append(
                Finding(
                    id=f"{relative}:accept-language",
                    rule_id="R26_robot_captcha_risk",
                    severity=Severity.MEDIUM,
                    summary="Requests do not ensure an Accept-Language header, increasing captcha risk.",
                    suggestion="Default Accept-Language via session.webRequest.onBeforeSendHeaders to mirror a real browser.",
                    file=relative,
                )
            )
    return findings
