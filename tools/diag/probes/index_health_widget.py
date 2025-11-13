from __future__ import annotations

from typing import Iterable, List

from ..engine import Finding, RuleContext, Severity
from . import register_probe


@register_probe(
    "probe_index_health_widget",
    description="Ensure index health endpoints and UI remain connected.",
    severity=Severity.HIGH,
)
def probe_index_health_widget(context: RuleContext) -> Iterable[Finding]:
    findings: List[Finding] = []

    service = context.read_text("backend/app/services/index_health.py")
    if "probe_all" not in (service or "") or "rebuild" not in (service or ""):
        findings.append(
            Finding(
                id="index_health:service",
                rule_id="probe_index_health_widget",
                severity=Severity.HIGH,
                summary="Index health service is missing probe_all/rebuild helpers.",
                suggestion="Implement probe_all and rebuild in backend/app/services/index_health.py.",
                file="backend/app/services/index_health.py",
            )
        )

    route = context.read_text("backend/app/api/index_health.py")
    if "/health" not in (route or "") or "/rebuild" not in (route or ""):
        findings.append(
            Finding(
                id="index_health:routes",
                rule_id="probe_index_health_widget",
                severity=Severity.HIGH,
                summary="Index health API routes are missing.",
                suggestion="Expose GET /api/index/health and POST /api/index/rebuild routes.",
                file="backend/app/api/index_health.py",
            )
        )

    badge = context.read_text(
        "frontend/src/components/index-health/IndexHealthBadge.tsx"
    )
    panel = context.read_text(
        "frontend/src/components/index-health/IndexHealthPanel.tsx"
    )
    if not badge or "/api/index/health" not in badge:
        findings.append(
            Finding(
                id="index_health:badge",
                rule_id="probe_index_health_widget",
                severity=Severity.MEDIUM,
                summary="Index health badge no longer fetches /api/index/health.",
                suggestion="Ensure IndexHealthBadge fetches /api/index/health to display status.",
                file="frontend/src/components/index-health/IndexHealthBadge.tsx",
            )
        )
    if not panel or "/api/index/rebuild" not in panel:
        findings.append(
            Finding(
                id="index_health:panel",
                rule_id="probe_index_health_widget",
                severity=Severity.MEDIUM,
                summary="Index health panel no longer posts to /api/index/rebuild.",
                suggestion="Ensure IndexHealthPanel offers a rebuild action.",
                file="frontend/src/components/index-health/IndexHealthPanel.tsx",
            )
        )

    makefile = context.read_text("Makefile")
    if makefile and "index-health" not in makefile:
        findings.append(
            Finding(
                id="index_health:cli",
                rule_id="probe_index_health_widget",
                severity=Severity.LOW,
                summary="Makefile helper targets for index health are missing.",
                suggestion="Add make index-health and index-rebuild shortcuts for quick probing.",
                file="Makefile",
            )
        )

    return findings


__all__ = ["probe_index_health_widget"]
