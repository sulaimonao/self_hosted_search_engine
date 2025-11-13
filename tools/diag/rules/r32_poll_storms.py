"""Flag hot polling loops that can overwhelm the renderer or backend."""

from __future__ import annotations

import re
from typing import Iterable, List

from ..engine import Finding, RuleContext, Severity, register
from ._react_utils import position_to_line, split_call_arguments

TARGET_PATTERNS = (
    "frontend/**/*.tsx",
    "frontend/**/*.ts",
    "frontend/**/*.jsx",
    "frontend/**/*.js",
)
INTERVAL_CALL_RE = re.compile(r"\bset(?P<kind>Interval|Timeout)\s*\(")
REFRESH_INTERVAL_RE = re.compile(r"refreshInterval\s*:\s*(\d+)")
MIN_SAFE_INTERVAL_MS = 3000


def _line_snippet(text: str, index: int) -> str:
    line_start = text.rfind("\n", 0, index) + 1
    line_end = text.find("\n", index)
    if line_end == -1:
        line_end = len(text)
    return text[line_start:line_end].strip()


@register(
    "R32_poll_storms",
    description="Aggressive timers and refresh intervals cause poll storms",
    severity=Severity.HIGH,
)
def rule_poll_storms(context: RuleContext) -> Iterable[Finding]:
    findings: List[Finding] = []
    for relative in context.iter_patterns(*TARGET_PATTERNS):
        if relative.endswith(".d.ts"):
            continue
        text = context.read_text(relative)
        for match in INTERVAL_CALL_RE.finditer(text):
            kind = match.group("kind")
            paren_index = text.find("(", match.start())
            if paren_index == -1:
                continue
            args, _ = split_call_arguments(text, paren_index)
            if len(args) < 2:
                continue
            delay_segment, delay_start, _delay_end = args[1]
            number_match = re.search(r"\b(\d+)\b", delay_segment)
            if not number_match:
                continue
            delay_ms = int(number_match.group(1))
            if delay_ms >= MIN_SAFE_INTERVAL_MS:
                continue
            findings.append(
                Finding(
                    id=f"poll-storm:{kind}:{delay_start}",
                    rule_id="R32_poll_storms",
                    severity=Severity.HIGH,
                    summary=(
                        f"`set{kind}` runs every {delay_ms} ms; anything under {MIN_SAFE_INTERVAL_MS} ms will slam the app."
                    ),
                    suggestion=(
                        "Increase the interval (≥3000 ms), debounce with SWR deduping, or collapse the timer behind server push."
                    ),
                    file=relative,
                    line_hint=position_to_line(text, match.start()),
                    evidence=_line_snippet(text, match.start()),
                )
            )
        for match in REFRESH_INTERVAL_RE.finditer(text):
            delay_ms = int(match.group(1))
            if delay_ms >= MIN_SAFE_INTERVAL_MS:
                continue
            index = match.start(1)
            findings.append(
                Finding(
                    id=f"poll-storm:swr:{index}",
                    rule_id="R32_poll_storms",
                    severity=Severity.HIGH,
                    summary=(
                        f"SWR refreshInterval is {delay_ms} ms; run cadence ≥{MIN_SAFE_INTERVAL_MS} ms to avoid poll storms."
                    ),
                    suggestion=(
                        "Use SWR's global `dedupingInterval` and raise component refreshInterval above 3000 ms or prefer SSE/webhooks."
                    ),
                    file=relative,
                    line_hint=position_to_line(text, index),
                    evidence=_line_snippet(text, index),
                )
            )
    return findings
