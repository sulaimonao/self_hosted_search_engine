"""Proxy risk diagnostics."""

from __future__ import annotations

import re
from typing import Iterable, List

from .engine import Finding, RuleContext, Severity, register

URL_RE = re.compile(
    r"(fetch|axios\.[a-zA-Z]+|requests\.(get|post|put|delete)|httpx\.(get|post|put|delete))\s*\(\s*['\"](https?://[^'\"]+)",
)
LOCAL_PREFIXES = (
    "http://localhost",
    "http://127.",
    "https://localhost",
    "https://127.",
)

DEFAULT_PORT_RE = re.compile(r"DEFAULT_API_BASE_URL\s*=\s*['\"`]http://[^:]+:(\d+)")
DESTINATION_PORT_RE = re.compile(
    r"destination\s*:\s*['\"`]http://[^:]+:(\d+)/api/:path\*"
)
BACKEND_PORT_RE = re.compile(r"BACKEND_PORT\s*=\s*(\d+)")


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


@register(
    "R25_proxy_cors_mismatch",
    description="Next.js rewrite and Flask CORS must target the same backend origin",
    severity=Severity.MEDIUM,
)
def rule_proxy_cors_mismatch(context: RuleContext) -> Iterable[Finding]:
    findings: List[Finding] = []

    config_text = context.read_text("frontend/next.config.mjs") or ""
    backend_text = context.read_text("backend/app/__init__.py") or ""
    env_text = context.read_text(".env.example") or ""

    if config_text:
        has_rewrite = "/api/:path*" in config_text and "destination" in config_text
        if not has_rewrite:
            findings.append(
                Finding(
                    id="proxy-cors:rewrite-missing",
                    rule_id="R25_proxy_cors_mismatch",
                    severity=Severity.MEDIUM,
                    summary="Next.js dev server is missing a rewrite for /api/* requests.",
                    suggestion="Add a rewrite in next.config.mjs forwarding /api/* to the Flask backend during development.",
                    file="frontend/next.config.mjs",
                )
            )

        proxy_port = None
        destination_match = DESTINATION_PORT_RE.search(config_text)
        if destination_match:
            proxy_port = destination_match.group(1)
        else:
            default_match = DEFAULT_PORT_RE.search(config_text)
            if default_match:
                proxy_port = default_match.group(1)

        backend_port = None
        env_match = BACKEND_PORT_RE.search(env_text)
        if env_match:
            backend_port = env_match.group(1)

        if proxy_port and backend_port and proxy_port != backend_port:
            findings.append(
                Finding(
                    id="proxy-cors:port-mismatch",
                    rule_id="R25_proxy_cors_mismatch",
                    severity=Severity.MEDIUM,
                    summary=f"Next.js rewrite targets port {proxy_port}, but .env example declares backend port {backend_port}.",
                    suggestion="Align NEXT_PUBLIC_API_BASE_URL or rewrites with BACKEND_PORT so the desktop proxy hits the correct Flask port.",
                    file="frontend/next.config.mjs",
                    evidence=f"rewrite_port={proxy_port}, env_port={backend_port}",
                )
            )

    if backend_text:
        if '"/api/*"' not in backend_text and "'/api/*'" not in backend_text:
            findings.append(
                Finding(
                    id="proxy-cors:cors-scope",
                    rule_id="R25_proxy_cors_mismatch",
                    severity=Severity.MEDIUM,
                    summary="Flask CORS configuration should be scoped to /api/* instead of all routes.",
                    suggestion="Restrict CORS(resources={r'/api/*': {...}}) to avoid exposing non-API endpoints to cross-origin requests.",
                    file="backend/app/__init__.py",
                )
            )
        if "app://renderer" not in backend_text:
            findings.append(
                Finding(
                    id="proxy-cors:renderer-origin",
                    rule_id="R25_proxy_cors_mismatch",
                    severity=Severity.MEDIUM,
                    summary="Desktop renderer origin (app://renderer) is missing from Flask CORS allowlist.",
                    suggestion="Add 'app://renderer' to the CORS origins so the packaged desktop app can call the API.",
                    file="backend/app/__init__.py",
                )
            )

    return findings
