from __future__ import annotations

from typing import Iterable, List

from ..engine import Finding, RuleContext, Severity
from . import register_probe


@register_probe(
    "probe_browsing_fallbacks",
    description="Ensure browsing fallback pipeline stays wired end-to-end.",
    severity=Severity.HIGH,
)
def probe_browsing_fallbacks(context: RuleContext) -> Iterable[Finding]:
    findings: List[Finding] = []

    service = context.read_text("backend/app/services/fallbacks.py")
    if "SmartFetcher" not in (service or "") or "FEED_PATHS" not in (service or ""):
        findings.append(
            Finding(
                id="browsing_fallbacks:service",
                rule_id="probe_browsing_fallbacks",
                severity=Severity.HIGH,
                summary="SmartFetcher fallbacks service is missing.",
                suggestion="Restore backend/app/services/fallbacks.py with SmartFetcher and FEED_PATHS constants.",
                file="backend/app/services/fallbacks.py",
            )
        )

    route = context.read_text("backend/app/api/browser.py")
    if "/fallback" not in (route or ""):
        findings.append(
            Finding(
                id="browsing_fallbacks:route",
                rule_id="probe_browsing_fallbacks",
                severity=Severity.HIGH,
                summary="/api/browser/fallback endpoint missing.",
                suggestion="Expose a GET /api/browser/fallback route that calls smart_fetch.",
                file="backend/app/api/browser.py",
            )
        )

    panel = context.read_text("frontend/src/components/panels/AgentLogPanel.tsx")
    if "/api/browser/fallback" not in (panel or ""):
        findings.append(
            Finding(
                id="browsing_fallbacks:panel",
                rule_id="probe_browsing_fallbacks",
                severity=Severity.MEDIUM,
                summary="Agent log panel no longer surfaces fallback strategies.",
                suggestion="Fetch /api/browser/fallback and render the returned items in AgentLogPanel.",
                file="frontend/src/components/panels/AgentLogPanel.tsx",
            )
        )

    return findings


__all__ = ["probe_browsing_fallbacks"]
