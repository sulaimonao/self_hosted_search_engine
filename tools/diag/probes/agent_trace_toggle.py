from __future__ import annotations

from typing import Iterable, List

from ..engine import Finding, RuleContext, Severity
from . import register_probe


def _line(text: str, needle: str) -> int | None:
    index = text.find(needle)
    if index == -1:
        return None
    return text.count("\n", 0, index) + 1


@register_probe(
    "probe_agent_trace_toggle",
    description="Ensure agent trace toggle and SSE endpoint stay wired up.",
    severity=Severity.HIGH,
)
def probe_agent_trace_toggle(context: RuleContext) -> Iterable[Finding]:
    findings: List[Finding] = []

    toggle = context.read_text("frontend/src/components/ReasoningToggle.tsx")
    if "Show agent steps" not in (toggle or ""):
        findings.append(
            Finding(
                id="agent_trace_toggle:missing_toggle",
                rule_id="probe_agent_trace_toggle",
                severity=Severity.HIGH,
                summary="Reasoning toggle component is missing or renamed.",
                suggestion="Restore frontend/src/components/ReasoningToggle.tsx with the Show agent steps label.",
                file="frontend/src/components/ReasoningToggle.tsx",
            )
        )

    store = context.read_text("frontend/src/state/ui.ts")
    # Accept either direct localStorage usage or the safeLocalStorage helper
    if not any(
        token in (store or "") for token in ("localStorage", "safeLocalStorage")
    ):
        findings.append(
            Finding(
                id="agent_trace_toggle:local_storage",
                rule_id="probe_agent_trace_toggle",
                severity=Severity.HIGH,
                summary="Reasoning toggle no longer persists to localStorage.",
                suggestion="Ensure frontend/src/state/ui.ts persists showReasoning to localStorage.",
                file="frontend/src/state/ui.ts",
                line_hint=_line(store or "", "localStorage"),
            )
        )

    backend = context.read_text("backend/app/api/agent_logs.py")
    if "/logs" not in (backend or "") or "event-stream" not in (backend or ""):
        findings.append(
            Finding(
                id="agent_trace_toggle:sse_endpoint",
                rule_id="probe_agent_trace_toggle",
                severity=Severity.HIGH,
                summary="/api/agent/logs SSE endpoint is missing.",
                suggestion="Expose backend/app/api/agent_logs.py with text/event-stream responses.",
                file="backend/app/api/agent_logs.py",
            )
        )

    tracing = context.read_text("backend/app/services/agent_tracing.py")
    if "redact" not in (tracing or ""):
        findings.append(
            Finding(
                id="agent_trace_toggle:redaction",
                rule_id="probe_agent_trace_toggle",
                severity=Severity.MEDIUM,
                summary="Agent tracing helper should redact sensitive args before publishing.",
                suggestion="Add redact_args/redact_value helpers in backend/app/services/agent_tracing.py.",
                file="backend/app/services/agent_tracing.py",
            )
        )

    return findings


__all__ = ["probe_agent_trace_toggle"]
