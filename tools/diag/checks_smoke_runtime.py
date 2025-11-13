"""Optional runtime smoke checks triggered via --smoke."""

from __future__ import annotations

from typing import Iterable, List

from .engine import Finding, RuleContext, Severity, register


@register(
    "S1",
    description="Ensure Electron runtime is available",
    severity=Severity.MEDIUM,
    smoke_only=True,
)
def smoke_electron_available(context: RuleContext) -> Iterable[Finding]:
    candidates = [
        context.root / "node_modules/.bin/electron",
        context.root / "frontend/node_modules/.bin/electron",
    ]
    for candidate in candidates:
        if candidate.exists():
            return []
    return [
        Finding(
            id="smoke:electron:missing",
            rule_id="S1",
            severity=Severity.MEDIUM,
            summary="Electron binary not found; desktop smoke tests skipped.",
            suggestion="Run npm install to provision Electron before executing --smoke diagnostics.",
            evidence=", ".join(str(path) for path in candidates),
        )
    ]


@register(
    "S2",
    description="Flask backend health endpoint responds",
    severity=Severity.MEDIUM,
    smoke_only=True,
)
def smoke_backend_health(_: RuleContext) -> Iterable[Finding]:
    findings: List[Finding] = []
    try:
        from backend.app import create_app
    except Exception as exc:  # pragma: no cover - defensive guard
        findings.append(
            Finding(
                id="smoke:backend:import",
                rule_id="S2",
                severity=Severity.MEDIUM,
                summary="Failed to import backend.app.create_app for smoke test.",
                suggestion="Ensure backend dependencies are installed before running smoke diagnostics.",
                evidence=str(exc),
            )
        )
        return findings
    try:
        app = create_app()
        with app.test_client() as client:
            response = client.get("/health")
            if response.status_code != 200:
                findings.append(
                    Finding(
                        id="smoke:backend:status",
                        rule_id="S2",
                        severity=Severity.MEDIUM,
                        summary="/health endpoint returned non-200 during smoke test.",
                        suggestion="Run backend diagnostics locally and ensure health endpoint remains stable.",
                        evidence=f"status={response.status_code}",
                    )
                )
    except Exception as exc:  # pragma: no cover - defensive guard
        findings.append(
            Finding(
                id="smoke:backend:error",
                rule_id="S2",
                severity=Severity.MEDIUM,
                summary="Backend smoke client raised an exception.",
                suggestion="Review backend startup logs; ensure create_app can run without external services in test mode.",
                evidence=str(exc),
            )
        )
    return findings
