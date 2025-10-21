"""Diagnostics package initialisation."""
from __future__ import annotations

from .engine import DiagnosticsEngine, ExitCode, Finding, Results, RuleContext, Severity, register, parse_fail_on

# Import rule packs so the decorators execute at import time.
from . import (  # noqa: F401
    checks_browser_shell,
    checks_electron_prefs,
    checks_headers,
    checks_meta,
    checks_next_build,
    checks_ports_scripts,
    checks_proxy_risk,
    checks_python_backend,
    checks_security_basics,
    checks_smoke_runtime,
)

__all__ = [
    "DiagnosticsEngine",
    "ExitCode",
    "Finding",
    "Results",
    "RuleContext",
    "Severity",
    "register",
    "parse_fail_on",
]
