"""Browser shell diagnostics focusing on iframe/webview usage."""
from __future__ import annotations

import re
from typing import Iterable, List

from .engine import Finding, RuleContext, Severity, register

IFRAME_RE = re.compile(r"<iframe[^>]*>", re.IGNORECASE)
SRC_RE = re.compile(r"src\s*=\s*['\"]([^'\"]+)['\"]", re.IGNORECASE)
CONTENT_HISTORY_RE = re.compile(r"contentWindow\.history\.(back|forward|go|pushState|replaceState)")
WEBVIEW_RE = re.compile(r"<webview", re.IGNORECASE)

THIRD_PARTY_HOSTS = ("http://", "https://", "//")
LOCAL_HOST_PREFIXES = ("http://localhost", "https://localhost", "http://127.", "https://127.")


@register(
    "R1",
    description="Browser shell should avoid third-party iframe navigation",
    severity=Severity.HIGH,
)
def rule_iframe_navigation(context: RuleContext) -> Iterable[Finding]:
    findings: List[Finding] = []
    for relative in context.iter_files(".tsx", ".ts", ".jsx", ".js", ".html"):
        text = context.read_text(relative)
        for match in IFRAME_RE.finditer(text):
            src_match = SRC_RE.search(match.group(0))
            src = src_match.group(1) if src_match else ""
            if not src:
                continue
            lowered = src.lower()
            if lowered.startswith(LOCAL_HOST_PREFIXES):
                continue
            if not lowered.startswith(THIRD_PARTY_HOSTS):
                # Treat dynamic values (e.g. {url}) as high risk to force review.
                if "{" not in src and "}" not in src:
                    continue
            line_no = text.count("\n", 0, match.start()) + 1
            findings.append(
                Finding(
                    id=f"{relative}:iframe:{line_no}",
                    rule_id="R1",
                    severity=Severity.HIGH,
                    summary="<iframe> navigates to a third-party origin, breaking desktop navigation controls.",
                    suggestion="Replace the iframe with Electron BrowserView/webview wiring and expose goBack()/goForward().",
                    file=relative,
                    line_hint=line_no,
                    evidence=src,
                )
            )
    return findings


@register(
    "R2",
    description="Avoid cross-origin history access via contentWindow",
    severity=Severity.HIGH,
)
def rule_content_window_history(context: RuleContext) -> Iterable[Finding]:
    findings: List[Finding] = []
    for relative in context.iter_files(".tsx", ".ts", ".jsx", ".js"):
        text = context.read_text(relative)
        for match in CONTENT_HISTORY_RE.finditer(text):
            line_no = text.count("\n", 0, match.start()) + 1
            findings.append(
                Finding(
                    id=f"{relative}:contentWindow:{line_no}",
                    rule_id="R2",
                    severity=Severity.HIGH,
                    summary="contentWindow.history access bypasses the trusted Electron navigation stack.",
                    suggestion="Use the main-process BrowserView history (webContents.goBack/goForward) instead of contentWindow.",
                    file=relative,
                    line_hint=line_no,
                    evidence=match.group(0),
                )
            )
    return findings


@register(
    "R3",
    description="Browser shell must use webview when browser components exist",
    severity=Severity.MEDIUM,
)
def rule_webview_presence(context: RuleContext) -> Iterable[Finding]:
    has_browser_component = any("browser" in relative.lower() for relative in context.iter_patterns("frontend/**", "desktop/**"))
    if not has_browser_component:
        return []
    for relative in context.iter_files(".tsx", ".ts", ".jsx", ".js", ".html"):
        text = context.read_text(relative)
        if WEBVIEW_RE.search(text):
            return []
    return [
        Finding(
            id="browser-shell:webview-missing",
            rule_id="R3",
            severity=Severity.MEDIUM,
            summary="Browser components detected but no <webview> usage found.",
            suggestion="Add an Electron <webview> (or BrowserView bridge) so desktop navigation can be hardened.",
            evidence="browser component files present",
        )
    ]
