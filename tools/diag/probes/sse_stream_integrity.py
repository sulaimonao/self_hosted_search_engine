"""Probe renderer SSE handling in frontend/src/hooks/useLlmStream.ts."""
from __future__ import annotations

import re
from typing import Iterable, List

from ..engine import Finding, RuleContext, Severity
from . import register_probe

TARGET = "frontend/src/hooks/useLlmStream.ts"


def _line_number(text: str, needle: str) -> int | None:
    index = text.find(needle)
    if index == -1:
        return None
    return text.count("\n", 0, index) + 1


@register_probe(
    "probe_sse_stream_integrity",
    description="Renderer LLM stream hook must parse SSE frames and expose a stable store",
    severity=Severity.HIGH,
)
def probe_sse_stream_integrity(context: RuleContext) -> Iterable[Finding]:
    """Ensure useLlmStream.ts keeps streaming semantics intact."""

    text = context.read_text(TARGET)
    if not text:
        return [
            Finding(
                id=f"{TARGET}:missing",
                rule_id="probe_sse_stream_integrity",
                severity=Severity.HIGH,
                summary="frontend/src/hooks/useLlmStream.ts is missing.",
                suggestion="Restore useLlmStream.ts with SSE frame parsing and a stable external store.",
                file=TARGET,
            )
        ]

    findings: List[Finding] = []

    if "useSyncExternalStore" not in text:
        findings.append(
            Finding(
                id=f"{TARGET}:useSyncExternalStore",
                rule_id="probe_sse_stream_integrity",
                severity=Severity.HIGH,
                summary="useLlmStream must rely on useSyncExternalStore to avoid render tearing.",
                suggestion="Wrap state consumers in useSyncExternalStore and emit updates through a shared store.",
                file=TARGET,
                line_hint=_line_number(text, "useLlmStream"),
            )
        )

    if "parseSseFrame" not in text or "data:" not in text:
        findings.append(
            Finding(
                id=f"{TARGET}:parseSseFrame",
                rule_id="probe_sse_stream_integrity",
                severity=Severity.HIGH,
                summary="SSE frames are not being parsed; expected parseSseFrame helper with data: extraction.",
                suggestion="Split incoming frames on data: prefixes and decode JSON payloads before applying.",
                file=TARGET,
                line_hint=_line_number(text, "parseSseFrame"),
            )
        )

    if "JSON.parse" not in text:
        findings.append(
            Finding(
                id=f"{TARGET}:json-parse",
                rule_id="probe_sse_stream_integrity",
                severity=Severity.HIGH,
                summary="SSE payloads should be decoded via JSON.parse before being applied to state.",
                suggestion="Decode SSE payload text with JSON.parse and guard against malformed frames.",
                file=TARGET,
            )
        )

    expected_events = ("metadata", "delta", "complete", "error")
    for event in expected_events:
        if re.search(rf"type\s*===\s*\"{event}\"", text) is None:
            findings.append(
                Finding(
                    id=f"{TARGET}:event-{event}",
                    rule_id="probe_sse_stream_integrity",
                    severity=Severity.MEDIUM,
                    summary=f"Streaming hook does not handle '{event}' SSE events.",
                    suggestion="Ensure applyFrame handles metadata, delta, complete, and error event types.",
                    file=TARGET,
                )
            )

    if "listeners = new Set" not in text:
        findings.append(
            Finding(
                id=f"{TARGET}:listener-set",
                rule_id="probe_sse_stream_integrity",
                severity=Severity.MEDIUM,
                summary="useLlmStream should maintain a shared Set of listeners for its external store.",
                suggestion="Keep a shared Set of listeners and notify them on each state mutation.",
                file=TARGET,
            )
        )

    return findings
