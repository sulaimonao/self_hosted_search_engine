"""Repository summary generator used by automated agents."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence

DIAG_CAPTURE_PATTERNS: Sequence[str] = (
    "@register",
    "Finding",
    "rule",
    "severity",
    "suggestion",
)
RULE_ID_REGEX = re.compile(r"@register\(\s*['\"]([A-Za-z0-9_:-]+)['\"]")


@dataclass(slots=True)
class FileSnippet:
    head: str
    tail: str
    matches: List[str]

    def to_dict(self) -> Dict[str, object]:
        payload: Dict[str, object] = {
            "head": self.head,
            "tail": self.tail,
        }
        if self.matches:
            payload["matches"] = self.matches
        return payload


def _gather_diag_snippets(root: Path) -> Dict[str, FileSnippet]:
    snippets: Dict[str, FileSnippet] = {}
    diag_root = root / "tools" / "diag"
    if not diag_root.exists():
        return snippets
    for path in sorted(diag_root.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        head = "\n".join(lines[:60])
        tail = "\n".join(lines[-60:]) if len(lines) > 60 else ""
        matched = [
            line
            for line in lines
            if any(token in line for token in DIAG_CAPTURE_PATTERNS)
        ]
        snippets[path.relative_to(root).as_posix()] = FileSnippet(
            head=head, tail=tail, matches=matched
        )
    return snippets


def _collect_rule_ids(snippets: Dict[str, FileSnippet]) -> List[str]:
    rule_ids: set[str] = set()
    for snippet in snippets.values():
        for candidate in RULE_ID_REGEX.findall(
            snippet.head + "\n" + snippet.tail + "\n".join(snippet.matches)
        ):
            rule_ids.add(candidate)
    return sorted(rule_ids)


def build_repo_summary(root: Path | None = None) -> Dict[str, object]:
    base = Path.cwd() if root is None else Path(root)
    diag_snippets = _gather_diag_snippets(base)
    summary: Dict[str, object] = {
        "diagnostics": {
            key: snippet.to_dict() for key, snippet in diag_snippets.items()
        },
        "diagnostics_rules": _collect_rule_ids(diag_snippets),
    }
    return summary


__all__ = ["build_repo_summary"]
