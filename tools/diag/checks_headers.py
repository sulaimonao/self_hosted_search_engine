"""Header manipulation diagnostics."""
from __future__ import annotations

import re
from typing import Iterable, List

from .engine import Finding, RuleContext, Severity, register

HOOK_RE = re.compile(r"onBeforeSendHeaders", re.IGNORECASE)


@register(
    "R9",
    description="Preserve Accept-Language and UA-CH headers",
    severity=Severity.MEDIUM,
)
def rule_headers_preserved(context: RuleContext) -> Iterable[Finding]:
    findings: List[Finding] = []
    patterns = (
        "electron/**/*.js",
        "electron/**/*.ts",
        "desktop/**/*.ts",
        "desktop/**/*.js",
        "electron/*.js",
        "electron/*.ts",
        "desktop/*.ts",
        "desktop/*.js",
        "backend/**/*.py",
    )
    for relative in context.iter_patterns(*patterns):
        text = context.read_text(relative)
        for match in HOOK_RE.finditer(text):
            segment = text[match.start() : match.start() + 400]
            if "requestHeaders" not in segment:
                continue
            has_accept_language = "Accept-Language" in segment or "accept-language" in segment
            has_ua_ch = "sec-ch-ua" in segment.lower()
            if has_accept_language and has_ua_ch:
                continue
            line_no = text.count("\n", 0, match.start()) + 1
            missing_parts = []
            if not has_accept_language:
                missing_parts.append("Accept-Language")
            if not has_ua_ch:
                missing_parts.append("sec-ch-ua*")
            findings.append(
                Finding(
                    id=f"{relative}:headers:{line_no}",
                    rule_id="R9",
                    severity=Severity.MEDIUM,
                    summary=f"onBeforeSendHeaders missing {', '.join(missing_parts)} pass-through.",
                    suggestion="Copy Accept-Language and all sec-ch-ua* headers into modified requests before returning them.",
                    file=relative,
                    line_hint=line_no,
                )
            )
    return findings
