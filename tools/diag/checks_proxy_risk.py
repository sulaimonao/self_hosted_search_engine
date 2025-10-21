"""Proxy risk diagnostics."""
from __future__ import annotations

import re
from typing import Iterable, List

from .engine import Finding, RuleContext, Severity, register

URL_RE = re.compile(
    r"(fetch|axios\.[a-zA-Z]+|requests\.(get|post|put|delete)|httpx\.(get|post|put|delete))\s*\(\s*['\"](https?://[^'\"]+)",
)
LOCAL_PREFIXES = ("http://localhost", "http://127.", "https://localhost", "https://127.")


@register(
    "R10",
    description="Avoid proxying external page loads through the app",
    severity=Severity.HIGH,
)
def rule_proxy_risk(context: RuleContext) -> Iterable[Finding]:
    findings: List[Finding] = []
    patterns = (
        "frontend/**/*.ts",
        "frontend/**/*.tsx",
        "frontend/**/*.js",
        "frontend/**/*.jsx",
        "desktop/**/*.ts",
        "desktop/**/*.js",
        "electron/**/*.js",
        "electron/**/*.ts",
        "backend/**/*.py",
        "server/**/*.py",
    )
    for relative in context.iter_patterns(*patterns):
        text = context.read_text(relative)
        for match in URL_RE.finditer(text):
            url = match.group(4)
            lowered = url.lower()
            if lowered.startswith(LOCAL_PREFIXES):
                continue
            line_no = text.count("\n", 0, match.start()) + 1
            findings.append(
                Finding(
                    id=f"{relative}:proxy:{line_no}",
                    rule_id="R10",
                    severity=Severity.HIGH,
                    summary="Direct fetch/axios call targets an external HTTPS origin; prefer letting Chromium handle navigation.",
                    suggestion="Remove the proxy fetch and let the renderer load the site directly, keeping proxies for first-party APIs only.",
                    file=relative,
                    line_hint=line_no,
                    evidence=url,
                )
            )
    return findings
