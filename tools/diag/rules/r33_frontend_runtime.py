"""Detect runtime frontend errors in logs that indicate TDZ or React render loops."""

from __future__ import annotations

import re
from typing import Iterable, List

from ..engine import Finding, RuleContext, Severity, register


@register(
    "R33_frontend_runtime",
    description="Detect frontend runtime errors like TDZ and React update depth in logs",
    severity=Severity.HIGH,
)
def rule_frontend_runtime(context: RuleContext) -> Iterable[Finding]:
    findings: List[Finding] = []
    # Look for log files and frontend runtime artifacts
    candidates = [
        "logs/frontend.log",
        "frontend/.next/trace.txt",
        "diagnostics/run_latest/frontend.log",
    ]
    # Also include any .log under logs/ or frontend/ that might be produced by runs
    for relative in context.iter_patterns(
        "logs/**/*.log", "frontend/**/*.log", "diagnostics/run_latest/**/*.log"
    ):
        candidates.append(relative)

    seen = set()
    for relative in candidates:
        if relative in seen:
            continue
        seen.add(relative)
        text = context.read_text(relative)
        if not text:
            continue
        # TDZ pattern
        for m in re.finditer(r"Cannot access '([^']+)' before initialization", text):
            name = m.group(1)
            idx = m.start()
            findings.append(
                Finding(
                    id=f"frontend-tdz:{name}:{relative}:{idx}",
                    rule_id="R33_frontend_runtime",
                    severity=Severity.HIGH,
                    summary=f"Front-end TDZ: Cannot access '{name}' before initialization in logs",
                    suggestion=(
                        "Move declarations (e.g. useRef/useState) to top-level of the component or "
                        "ensure initialization before use; guard access behind client-only checks."
                    ),
                    file=relative,
                    line_hint=None,
                    evidence=m.group(0),
                )
            )

        # React update depth pattern
        for m in re.finditer(r"Maximum update depth exceeded", text):
            idx = m.start()
            # capture a small surrounding snippet
            start = max(0, idx - 80)
            end = min(len(text), idx + 80)
            snippet = text[start:end].strip()
            findings.append(
                Finding(
                    id=f"react-loop-runtime:{relative}:{idx}",
                    rule_id="R33_frontend_runtime",
                    severity=Severity.HIGH,
                    summary="React runtime detected Maximum update depth exceeded",
                    suggestion=(
                        "Guard effects to avoid updating state they depend on; compare with refs "
                        "or remove circular dependencies from effect deps."
                    ),
                    file=relative,
                    line_hint=None,
                    evidence=snippet,
                )
            )

    return findings
