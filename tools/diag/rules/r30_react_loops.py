"""Detect React effects that are guaranteed to re-trigger themselves."""
from __future__ import annotations

import re
from typing import Iterable, List

from ..engine import Finding, RuleContext, Severity, register
from ._react_utils import collect_state_setters, iter_effect_blocks

TARGET_PATTERNS = ("frontend/**/*.tsx", "frontend/**/*.ts", "frontend/**/*.jsx", "frontend/**/*.js")


@register(
    "R30_react_loop",
    description="Effects that update state they depend on can cause render loops",
    severity=Severity.HIGH,
)
def rule_react_loops(context: RuleContext) -> Iterable[Finding]:
    findings: List[Finding] = []
    for relative in context.iter_patterns(*TARGET_PATTERNS):
        if relative.endswith(".d.ts"):
            continue
        text = context.read_text(relative)
        if "useEffect" not in text and "useLayoutEffect" not in text:
            continue
        state_map = collect_state_setters(text)
        if not state_map:
            continue
        setters = {setter: state for state, setter in state_map.items()}
        blocks = iter_effect_blocks(text)
        for block in blocks:
            if not block.deps:
                continue
            triggered_states: List[str] = []
            for setter, state in setters.items():
                if not re.search(rf"\b{re.escape(setter)}\s*\(", block.body):
                    continue
                if any(dep == state or dep.startswith(f"{state}.") for dep in block.deps):
                    triggered_states.append(state)
            if not triggered_states:
                continue
            summary_states = ", ".join(sorted(set(triggered_states)))
            findings.append(
                Finding(
                    id=f"react-loop:{summary_states}",
                    rule_id="R30_react_loop",
                    severity=Severity.HIGH,
                    summary=(
                        f"useEffect updates {summary_states} while depending on the same state, "
                        "which will re-trigger itself and can lock the render loop."
                    ),
                    suggestion=(
                        "Guard the state update (e.g. compare previous values with refs) or "
                        "remove the state from the dependency array to avoid self-triggering effects."
                    ),
                    file=relative,
                    line_hint=block.line,
                    evidence=block.body.strip()[:200] or None,
                )
            )
    return findings
