"""Playwright parity probe for render loop guard diagnostics."""

from __future__ import annotations

import os
import subprocess
from typing import Iterable, List

from ..engine import Finding, RuleContext, Severity
from . import register_probe


def _run_playwright(
    root: os.PathLike[str], url: str
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PLAYWRIGHT_APP_URL"] = url
    command = [
        "npm",
        "--prefix",
        "frontend",
        "exec",
        "--",
        "playwright",
        "test",
        "-c",
        "frontend/playwright.config.ts",
        "frontend/tests/e2e/render-loop.spec.ts",
        "--reporter",
        "line",
    ]
    return subprocess.run(
        command,
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


@register_probe(
    "REACT_RENDER_LOOP",
    description="Ensure render loop guard prevents runaway renders in web & desktop shells.",
    severity=Severity.HIGH,
)
def probe_render_loop_guard(context: RuleContext) -> Iterable[Finding]:
    findings: List[Finding] = []

    default_url = os.environ.get("PLAYWRIGHT_WEB_URL", "http://127.0.0.1:3100")
    desktop_url = os.environ.get("DESKTOP_RENDERER_URL") or os.environ.get(
        "RENDERER_URL"
    )

    targets = [("web", default_url)]
    if desktop_url and desktop_url.strip() and desktop_url.strip() != default_url:
        targets.append(("desktop", desktop_url.strip()))

    for label, url in targets:
        result = _run_playwright(context.root, url)
        if result.returncode != 0:
            summary = f"Playwright render loop guard check failed for {label}."
            suggestion = (
                "Review console output for [render-loop] markers. Guard should suppress infinite rerenders "
                "before shipping."
            )
            findings.append(
                Finding(
                    id=f"render-loop:{label}",
                    rule_id="REACT_RENDER_LOOP",
                    severity=Severity.HIGH,
                    summary=summary,
                    suggestion=suggestion,
                    evidence=(result.stdout or "") + "\n" + (result.stderr or ""),
                )
            )

    return findings


__all__ = ["probe_render_loop_guard"]
