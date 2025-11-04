"""Diagnostics package initialisation."""
from __future__ import annotations

from .engine import DiagnosticsEngine, ExitCode, Finding, Results, RuleContext, Severity, register, parse_fail_on
from .probes import Probe, iter_probes

# Import rule packs so the decorators execute at import time.
from . import (  # noqa: F401
    checks_browser_shell,
    checks_electron_prefs,
    checks_headers,
    checks_llm_stream,
    checks_meta,
    checks_next_build,
    checks_ports_scripts,
    checks_proxy_risk,
    checks_python_backend,
    checks_security_basics,
    checks_smoke_runtime,
)
from .rules import env_keys_example  # noqa: F401
from .rules import pyproject_vs_requirements  # noqa: F401
from .rules import r30_react_loops  # noqa: F401
from .rules import r31_hydration_risks  # noqa: F401
from .rules import r32_poll_storms  # noqa: F401
from .probes import (  # noqa: F401
    agent_trace_toggle,
    auth_clearance_profiles,
    browsing_fallbacks,
    electron_webprefs,
    headers_pass,
    index_health_widget,
    sse_stream_integrity,
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
    "Probe",
    "iter_probes",
]
