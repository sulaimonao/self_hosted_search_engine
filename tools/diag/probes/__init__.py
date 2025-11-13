"""Probe registration helpers for targeted diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Iterable, Iterator

from ..engine import Finding, RuleContext, Severity, register


@dataclass
class Probe:
    """Descriptor for a targeted diagnostic probe."""

    id: str
    description: str
    severity: Severity
    check: Callable[[RuleContext], Iterable[Finding]]


_PROBES: Dict[str, Probe] = {}


def register_probe(
    probe_id: str,
    *,
    description: str,
    severity: Severity = Severity.HIGH,
    smoke_only: bool = False,
) -> Callable[
    [Callable[[RuleContext], Iterable[Finding]]],
    Callable[[RuleContext], Iterable[Finding]],
]:
    """Register a probe and expose it as a diagnostic rule.

    Probes can be marked smoke_only so they're only executed when the engine
    runs with smoke=True (e.g. in environments where services are available).
    """

    def decorator(func: Callable[[RuleContext], Iterable[Finding]]):
        register(
            probe_id, description=description, severity=severity, smoke_only=smoke_only
        )(func)
        if probe_id in _PROBES:
            raise ValueError(f"Probe '{probe_id}' already registered")
        _PROBES[probe_id] = Probe(
            id=probe_id,
            description=description,
            severity=severity,
            check=func,
        )
        return func

    return decorator


def iter_probes() -> Iterator[Probe]:
    """Iterate over registered probes in a stable order."""

    for probe_id in sorted(_PROBES):
        yield _PROBES[probe_id]


__all__ = ["Probe", "register_probe", "iter_probes"]
