from __future__ import annotations

from typing import Iterable, List

from ..engine import Finding, RuleContext, Severity
from . import register_probe


@register_probe(
    "probe_auth_clearance_profiles",
    description="Ensure domain clearance detection and persistence stay intact.",
    severity=Severity.HIGH,
)
def probe_auth_clearance_profiles(context: RuleContext) -> Iterable[Finding]:
    findings: List[Finding] = []

    service = context.read_text("backend/app/services/auth_clearance.py")
    if "detect_clearance" not in (service or ""):
        findings.append(
            Finding(
                id="auth_clearance:service",
                rule_id="probe_auth_clearance_profiles",
                severity=Severity.HIGH,
                summary="Auth clearance detection helper is missing.",
                suggestion="Add detect_clearance in backend/app/services/auth_clearance.py.",
                file="backend/app/services/auth_clearance.py",
            )
        )

    db_layer = context.read_text("backend/app/db/domain_profiles.py")
    if "CREATE TABLE IF NOT EXISTS domain_profiles" not in (db_layer or ""):
        findings.append(
            Finding(
                id="auth_clearance:db",
                rule_id="probe_auth_clearance_profiles",
                severity=Severity.HIGH,
                summary="Domain profiles SQLite table definition missing.",
                suggestion="Ensure backend/app/db/domain_profiles.py manages the domain_profiles table.",
                file="backend/app/db/domain_profiles.py",
            )
        )

    routes = context.read_text("backend/app/api/domain_profiles.py")
    if "/api/domain_profiles" not in (routes or ""):
        findings.append(
            Finding(
                id="auth_clearance:routes",
                rule_id="probe_auth_clearance_profiles",
                severity=Severity.MEDIUM,
                summary="Domain profile API endpoints missing.",
                suggestion="Expose list and detail routes for domain profiles.",
                file="backend/app/api/domain_profiles.py",
            )
        )

    crawl_client = context.read_text("engine/indexing/crawl.py")
    if "clearance_callback" not in (crawl_client or ""):
        findings.append(
            Finding(
                id="auth_clearance:crawl_callback",
                rule_id="probe_auth_clearance_profiles",
                severity=Severity.MEDIUM,
                summary="Crawl client does not invoke the clearance callback.",
                suggestion="Wire clearance_callback into CrawlClient so fetches record paywall/login signals.",
                file="engine/indexing/crawl.py",
            )
        )

    return findings


__all__ = ["probe_auth_clearance_profiles"]
