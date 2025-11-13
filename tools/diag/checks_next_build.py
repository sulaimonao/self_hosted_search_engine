"""Next.js build configuration diagnostics."""

from __future__ import annotations

import re
from typing import Iterable, List

from .engine import Finding, RuleContext, Severity, register

XFO_RE = re.compile(r"X-Frame-Options", re.IGNORECASE)
CSP_RE = re.compile(r"Content-Security-Policy", re.IGNORECASE)
FRAME_DENY_RE = re.compile(
    r"frame-ancestors[^;]*('none'|none|deny|DENY)", re.IGNORECASE
)
IMAGES_RE = re.compile(r"images\s*:\s*\{[^}]*domains\s*:\s*\[", re.DOTALL)
REMOTE_IMAGE_RE = re.compile(r"<Image[^>]*src=\s*['\"]https?://([a-zA-Z0-9.-]+)")


@register(
    "R12",
    description="Review Next.js config for restrictive headers or missing domains",
    severity=Severity.MEDIUM,
)
def rule_next_config(context: RuleContext) -> Iterable[Finding]:
    findings: List[Finding] = []
    config_patterns = (
        "frontend/next.config.*",
        "frontend/**/next.config.*",
    )
    remote_domains: set[str] = set()
    for relative in context.iter_patterns(
        "frontend/src/**/*.tsx", "frontend/src/**/*.ts", "frontend/src/**/*.jsx"
    ):
        text = context.read_text(relative)
        for match in REMOTE_IMAGE_RE.finditer(text):
            remote_domains.add(match.group(1))
    for relative in context.iter_patterns(*config_patterns):
        text = context.read_text(relative)
        line_base = 1
        if XFO_RE.search(text):
            if "DENY" in text or "SAMEORIGIN" in text.upper():
                line_no = text.count("\n", 0, text.find("X-Frame-Options")) + line_base
                findings.append(
                    Finding(
                        id=f"{relative}:xfo:{line_no}",
                        rule_id="R12",
                        severity=Severity.MEDIUM,
                        summary="Next.js headers set X-Frame-Options preventing the app shell from embedding itself.",
                        suggestion="Remove X-Frame-Options for first-party routes or scope it away from the desktop shell paths.",
                        file=relative,
                        line_hint=line_no,
                    )
                )
        if CSP_RE.search(text) and FRAME_DENY_RE.search(text):
            line_no = (
                text.count("\n", 0, text.find("Content-Security-Policy")) + line_base
            )
            findings.append(
                Finding(
                    id=f"{relative}:csp:{line_no}",
                    rule_id="R12",
                    severity=Severity.MEDIUM,
                    summary="Content-Security-Policy frame-ancestors blocks the embedded desktop browser shell.",
                    suggestion="Allow frame-ancestors 'self' or the desktop scheme when serving the browser shell.",
                    file=relative,
                    line_hint=line_no,
                )
            )
        if remote_domains and not IMAGES_RE.search(text):
            findings.append(
                Finding(
                    id=f"{relative}:images-domains",
                    rule_id="R12",
                    severity=Severity.MEDIUM,
                    summary="Remote <Image> sources detected but next.config lacks images.domains.",
                    suggestion="Add images.domains with the remote hosts used in <Image src> to avoid runtime failures.",
                    file=relative,
                )
            )
    return findings
