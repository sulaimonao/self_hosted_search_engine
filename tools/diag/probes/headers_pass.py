"""Probe Electron request header pass-through in desktop/main.ts."""

from __future__ import annotations

import re
from typing import Iterable, List

from ..engine import Finding, RuleContext, Severity
from . import register_probe

TARGET = "desktop/main.ts"


def _hook_segment(text: str) -> str:
    start = text.find("webRequest.onBeforeSendHeaders")
    if start == -1:
        return ""
    brace_start = text.find("{", start)
    if brace_start == -1:
        return ""
    depth = 0
    for index in range(brace_start, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return text[start:]


def _line_number(text: str, needle: str) -> int | None:
    index = text.find(needle)
    if index == -1:
        return None
    return text.count("\n", 0, index) + 1


@register_probe(
    "probe_headers_pass",
    description="Desktop main process must preserve Accept-Language when rewriting headers",
    severity=Severity.MEDIUM,
)
def probe_headers_pass(context: RuleContext) -> Iterable[Finding]:
    """Ensure desktop/main.ts clones incoming headers before modifications."""

    text = context.read_text(TARGET)
    if not text:
        return [
            Finding(
                id=f"{TARGET}:missing",
                rule_id="probe_headers_pass",
                severity=Severity.MEDIUM,
                summary="desktop/main.ts is missing; cannot verify header pass-through.",
                suggestion="Restore desktop/main.ts so the Electron session keeps Accept-Language intact.",
                file=TARGET,
            )
        ]

    findings: List[Finding] = []

    if "webRequest.onBeforeSendHeaders" not in text:
        findings.append(
            Finding(
                id=f"{TARGET}:hook-missing",
                rule_id="probe_headers_pass",
                severity=Severity.MEDIUM,
                summary="Electron session must intercept onBeforeSendHeaders to normalise headers.",
                suggestion="Add mainSession.webRequest.onBeforeSendHeaders to adjust user agent while preserving Accept-Language.",
                file=TARGET,
            )
        )
        return findings

    segment = _hook_segment(text)
    if (
        "...details.requestHeaders" not in segment
        and "Object.assign({}, details.requestHeaders" not in segment
    ):
        findings.append(
            Finding(
                id=f"{TARGET}:missing-spread",
                rule_id="probe_headers_pass",
                severity=Severity.HIGH,
                summary="Headers hook should spread details.requestHeaders before overriding values.",
                suggestion="Start from { ...details.requestHeaders } so Accept-Language and client hints pass through.",
                file=TARGET,
                line_hint=_line_number(text, "webRequest.onBeforeSendHeaders"),
            )
        )

    if re.search(r"delete\s+headers\[['\"]Accept-Language['\"]\]", segment):
        findings.append(
            Finding(
                id=f"{TARGET}:accept-language-deleted",
                rule_id="probe_headers_pass",
                severity=Severity.HIGH,
                summary="Headers hook deletes Accept-Language, which breaks locale negotiation.",
                suggestion="Do not remove Accept-Language when normalising Electron request headers.",
                file=TARGET,
                line_hint=_line_number(text, "Accept-Language"),
            )
        )

    if not re.search(r"callback\(\{\s*requestHeaders\s*:\s*headers\s*\}\)", segment):
        findings.append(
            Finding(
                id=f"{TARGET}:callback-missing",
                rule_id="probe_headers_pass",
                severity=Severity.MEDIUM,
                summary="Headers hook should pass the modified headers object back to Electron.",
                suggestion="Call callback({ requestHeaders: headers }) after adjustments.",
                file=TARGET,
            )
        )

    return findings
