"""Flag render-time access to browser-only globals that break hydration."""
from __future__ import annotations

import re
from typing import Iterable, List

from ..engine import Finding, RuleContext, Severity, register
from ._react_utils import inside_effect, iter_effect_blocks, position_to_line

TARGET_PATTERNS = ("frontend/**/*.tsx", "frontend/**/*.ts", "frontend/**/*.jsx", "frontend/**/*.js")
TOKEN_RE = re.compile(r"\b(window|document|navigator|localStorage|sessionStorage)\b")


@register(
    "R31_hydration_risk",
    description="Render-time browser globals will desync server and client DOM",
    severity=Severity.MEDIUM,
)
def rule_hydration_risks(context: RuleContext) -> Iterable[Finding]:
    findings: List[Finding] = []
    for relative in context.iter_patterns(*TARGET_PATTERNS):
        if relative.endswith(".d.ts"):
            continue
        if not relative.startswith("frontend/"):
            continue
        text = context.read_text(relative)
        matches = list(TOKEN_RE.finditer(text))
        if not matches:
            continue
        blocks = iter_effect_blocks(text)
        for match in matches:
            token = match.group(1)
            index = match.start()
            if inside_effect(index, blocks):
                continue
            if index > 0 and text[index - 1] in {"'", '"', "`"}:
                continue
            line_start = text.rfind("\n", 0, index) + 1
            line_end = text.find("\n", index)
            if line_end == -1:
                line_end = len(text)
            line_text = text[line_start:line_end]
            prefix = line_text[: index - line_start]
            if "//" in prefix:
                continue
            if f"typeof {token}" in line_text:
                continue
            if token == "window" and "globalThis" in line_text:
                continue
            findings.append(
                Finding(
                    id=f"hydration-risk:{token}:{index}",
                    rule_id="R31_hydration_risk",
                    severity=Severity.MEDIUM,
                    summary=(
                        f"Direct render-time access to `{token}` risks server/client divergence during hydration."
                    ),
                    suggestion=(
                        "Wrap the access in `useEffect`, guard with `typeof window !== 'undefined'`, "
                        "or gate the render path behind a client-ready check."
                    ),
                    file=relative,
                    line_hint=position_to_line(text, index),
                    evidence=line_text.strip() or None,
                )
            )
    return findings
