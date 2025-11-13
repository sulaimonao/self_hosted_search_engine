"""Playwright probe to ensure chat messages render in both renderers."""

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
        "frontend/tests/e2e/chat-visibility.spec.ts",
        "--reporter",
        "line",
    ]
    return subprocess.run(
        command, cwd=root, text=True, capture_output=True, check=False, env=env
    )


@register_probe(
    "probe_chat_visibility_e2e",
    description="E2E: Chat UI renders user and assistant messages (useChat + manual)",
    severity=Severity.HIGH,
)
def probe_chat_visibility_e2e(context: RuleContext) -> Iterable[Finding]:
    findings: List[Finding] = []

    # Only run this heavy E2E when smoke mode is enabled.
    if not context.smoke:
        return findings

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
            findings.append(
                Finding(
                    id=f"chat-visibility:{label}",
                    rule_id="probe_chat_visibility_e2e",
                    severity=Severity.HIGH,
                    summary=f"Chat visibility e2e failed for {label}.",
                    suggestion=(
                        "Ensure ChatPanelUseChat concatenates UIMessage.parts[].text and the model selector is wired."
                        " Verify servers running and PLAYWRIGHT_APP_URL is reachable."
                    ),
                    evidence=(result.stdout or "") + "\n" + (result.stderr or ""),
                )
            )

    return findings
