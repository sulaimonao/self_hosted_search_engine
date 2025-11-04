from __future__ import annotations

import os
import shutil
import subprocess
from typing import Iterable, List

from ..engine import Finding, RuleContext, Severity
from . import register_probe


@register_probe(
    "REACT_RENDER_LOOP",
    description="Playwright render loop guard remains stable in web and desktop shells.",
    severity=Severity.HIGH,
)
def probe_react_render_loop(context: RuleContext) -> Iterable[Finding]:
    findings: List[Finding] = []
    npx_bin = shutil.which("npx")
    if not npx_bin:
        findings.append(
            Finding(
                id="react-render-loop:npx-missing",
                rule_id="REACT_RENDER_LOOP",
                severity=Severity.HIGH,
                summary="npx not available to run Playwright diagnostics.",
                suggestion="Install Node.js tooling (including npx) before running diagnostics.",
            )
        )
        return findings

    commands = []
    web_base = os.getenv("APP_BASE_URL", "http://localhost:3100")
    commands.append(("web", web_base))
    desktop_base = os.getenv("DESKTOP_RENDERER_URL")
    if desktop_base:
        commands.append(("desktop", desktop_base))

    for target, base_url in commands:
        env = os.environ.copy()
        env["APP_BASE_URL"] = base_url
        env["PLAYWRIGHT_TARGET"] = target
        result = subprocess.run(
            [npx_bin, "playwright", "test", "e2e/render_loop.spec.ts"],
            cwd=context.root,
            capture_output=True,
            text=True,
            env=env,
        )
        if result.returncode != 0:
            evidence = "\n".join(
                part.strip()
                for part in [result.stdout or "", result.stderr or ""]
                if part and part.strip()
            )
            findings.append(
                Finding(
                    id=f"react-render-loop:{target}",
                    rule_id="REACT_RENDER_LOOP",
                    severity=Severity.HIGH,
                    summary=f"Playwright render loop guard failed for {target} shell.",
                    suggestion="Inspect frontend console output for [render-loop] markers and stabilise effect dependencies.",
                    evidence=evidence[:4000] if evidence else None,
                )
            )
    return findings


__all__ = ["probe_react_render_loop"]
