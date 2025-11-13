"""Meta diagnostics that keep the rule engine evolving with the repo."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, List, Set

from .engine import Finding, RuleContext, Severity, register
from .globs import EXCLUDE_DIRS, EXTENSION_TO_TYPE


@register(
    "META_GLOBS",
    description="Update diagnostics globs when new file types appear",
    severity=Severity.MEDIUM,
)
def rule_unknown_file_types(context: RuleContext) -> Iterable[Finding]:
    known_suffixes: Set[str] = set(EXTENSION_TO_TYPE.keys())
    unknown_suffixes = sorted(
        suffix
        for suffix in context.unmatched_suffixes
        if suffix and suffix not in known_suffixes
    )
    if not unknown_suffixes:
        return []

    sample_paths: List[str] = []
    for dirpath, dirnames, filenames in os.walk(context.root):
        dirnames[:] = [name for name in dirnames if name not in EXCLUDE_DIRS]
        for filename in filenames:
            suffix = Path(filename).suffix.lower()
            if suffix in unknown_suffixes:
                relative = Path(dirpath, filename).relative_to(context.root).as_posix()
                sample_paths.append(relative)
        if len(sample_paths) >= 5:
            break

    summary_suffixes = ", ".join(unknown_suffixes)
    evidence = ", ".join(sample_paths) if sample_paths else None
    return [
        Finding(
            id="meta:unknown-globs",
            rule_id="META_GLOBS",
            severity=Severity.MEDIUM,
            summary=f"New file suffixes detected that are not covered by tools/diag/globs.py: {summary_suffixes}.",
            suggestion="Update tools/diag/globs.py FILE_GLOBS to include these extensions so future rules can inspect them.",
            evidence=evidence,
        )
    ]
