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
        # skip files that explicitly opt into client-only execution
        prefix = text[:200]
        if "'use client'" in prefix or '"use client"' in prefix:
            continue
        matches = list(TOKEN_RE.finditer(text))
        if not matches:
            continue
        blocks = iter_effect_blocks(text)
        for match in matches:
            token = match.group(1)
            index = match.start()
            # skip if inside a React effect block (we expect guarded runtime use there)
            if inside_effect(index, blocks):
                continue
            # simple heuristic: skip if this occurrence is inside a string literal
            # by checking for a matching quote before and after the index
            def _inside_string(idx: int) -> bool:
                for quote in ("'", '"', "`"):
                    prev = text.rfind(quote, 0, idx)
                    nxt = text.find(quote, idx)
                    if prev != -1 and nxt != -1:
                        # ensure the quote characters are not escaped (rough check)
                        if prev == 0 or text[prev - 1] != "\\":
                            return True
                return False

            if _inside_string(index):
                continue
            # skip if this token is likely used as a type or object key (e.g. 'document:')
            after_char = text[index + len(token) : index + len(token) + 1]
            if after_char == ":":
                continue
            # skip if a nearby typeof guard exists earlier in the file (within 200 chars)
            lookback = max(0, index - 200)
            if f"typeof {token}" in text[lookback:index]:
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
