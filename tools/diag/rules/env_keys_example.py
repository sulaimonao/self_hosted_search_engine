"""Ensure environment keys referenced in code are documented."""
from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path
from typing import Iterable, List, Set

from ..engine import Finding, RuleContext, Severity, register

ENV_CALL_RE = re.compile(
    r"(?:os\.(?:environ\[['\"]|getenv\(['\"])|process\.env\.)([A-Z0-9_]+)"
)
ENV_ASSIGN_RE = re.compile(r"^\s*([A-Z0-9_]+)\s*=", re.MULTILINE)
IGNORED_ENV = {"NODE_ENV", "PORT", "PYTHONPATH", "PATH", "HOME", "DEBUG"}
ENV_EXAMPLE_PATTERNS = ("*.env.example", "**/.env.example", "**/.env")
SOURCE_PATTERNS = ("**/*.py", "**/*.ts", "**/*.tsx", "**/*.js")
DEFAULT_APP_STATE_DB = Path("data/app_state.sqlite3")


def _load_app_config_keys(context: RuleContext) -> Set[str]:
    """Read documented keys from the runtime app_config table when available."""

    candidates = []
    for env_var in ("APP_STATE_DB_PATH", "APP_STATE_DB"):
        configured = os.getenv(env_var)
        if configured:
            candidates.append(Path(configured))
    candidates.append(DEFAULT_APP_STATE_DB)

    root = context.root
    seen: Set[Path] = set()
    for candidate in candidates:
        path = candidate if candidate.is_absolute() else root / candidate
        if path in seen:
            continue
        seen.add(path)
        if not path.exists():
            continue
        try:
            connection = sqlite3.connect(str(path))
        except sqlite3.Error:
            continue
        try:
            cursor = connection.execute("SELECT k FROM app_config")
            keys: Set[str] = set()
            for raw_key, in cursor.fetchall():
                if raw_key is None:
                    continue
                base = str(raw_key).strip()
                if not base:
                    continue
                keys.add(base)
                canonical = re.sub(r"[^A-Za-z0-9]+", "_", base).strip("_").upper()
                if canonical:
                    keys.add(canonical)
            return keys
        except sqlite3.Error:
            return set()
        finally:
            connection.close()
    return set()


@register(
    "R14",
    description="Document environment variables in .env.example",
    severity=Severity.MEDIUM,
)
def rule_env_examples(context: RuleContext) -> Iterable[Finding]:
    findings: List[Finding] = []
    referenced: Set[str] = set()
    for relative in context.iter_patterns(*SOURCE_PATTERNS):
        text = context.read_text(relative)
        for match in ENV_CALL_RE.finditer(text):
            key = match.group(1)
            if key not in IGNORED_ENV:
                referenced.add(key)
    example_keys: Set[str] = set()
    for relative in context.iter_patterns(*ENV_EXAMPLE_PATTERNS):
        text = context.read_text(relative)
        for key in ENV_ASSIGN_RE.findall(text):
            example_keys.add(key)
    app_config_keys = _load_app_config_keys(context)
    documented = example_keys | app_config_keys
    missing = sorted(key for key in referenced if key not in documented)
    if missing:
        findings.append(
            Finding(
                id="env:missing-example",
                rule_id="R14",
                severity=Severity.MEDIUM,
                summary=(
                    "Environment keys referenced in code lack .env.example entries: "
                    + ", ".join(missing)
                    + "."
                ),
                suggestion="Add the missing keys to .env.example with safe defaults or documentation.",
            )
        )
    return findings
