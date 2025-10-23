"""File scanning configuration for diagnostics.

This module centralises the default repository globs and file type metadata
used by the diagnostics engine. The meta-rule relies on this list to detect new
file types so keep it in sync when adding technologies to the project.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence, Set

# Directories that should be ignored when scanning the repository. They typically
# contain third-party artefacts or build outputs that the diagnostics must not
# traverse. The values are directory *names* (not paths) that are pruned during
# the walk.
EXCLUDE_DIRS: Set[str] = {
    ".git",
    "node_modules",
    "dist",
    "build",
    "out",
    ".next",
    "diagnostics",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".cache",
    "venv",
    ".venv",
    "env",
    "tmp",
}

# Default globs per logical file type. The engine flattens this structure to
# build the initial file set and to understand which extensions are expected.
FILE_GLOBS: Dict[str, Sequence[str]] = {
    "python": ("**/*.py",),
    "javascript": ("**/*.js", "**/*.mjs", "**/*.cjs"),
    "typescript": ("**/*.ts", "**/*.tsx"),
    "jsx": ("**/*.jsx",),
    "json": ("**/*.json",),
    "yaml": ("**/*.yaml", "**/*.yml"),
    "toml": ("**/*.toml",),
    "ini": ("**/*.ini",),
    "html": ("**/*.html", "**/*.htm"),
    "css": ("**/*.css",),
    "shell": ("**/*.sh", "**/*.bash"),
    "markdown": ("**/*.md", "**/*.mdx"),
    "text": ("**/*.txt",),
    "sql": ("**/*.sql",),
    "images": ("**/*.svg", "**/*.ico"),
    "artifacts": (
        "**/*.log",
        "**/*.jsonl",
        "**/*.ndjson",
        "**/*.duckdb",
        "**/*.sqlite",
        "**/*.sqlite3",
        "**/*.sqlite-wal",
        "**/*.sqlite3-wal",
        "**/*.sqlite-shm",
        "**/*.sqlite3-shm",
        "**/*.seg",
        "**/*.toc",
        "**/*.bin",
    ),
    "lockfiles": (
        "**/package-lock.json",
        "**/pnpm-lock.yaml",
        "**/yarn.lock",
        "**/poetry.lock",
        "**/requirements*.txt",
        "**/Pipfile",
        "**/Pipfile.lock",
    ),
    "config": (
        "**/.env",
        "**/.env.*",
        "**/config.*",
        "**/*.config.*",
        "**/*.conf",
        "**/*.cfg",
    ),
    "html_like": ("**/*.vue", "**/*.svelte"),
}

# Explicit filenames that do not carry a meaningful extension but are important
# for diagnostics. They are considered known types to avoid triggering the
# meta-rule.
SPECIAL_FILENAMES: Dict[str, str] = {
    "Dockerfile": "dockerfile",
    "Makefile": "make",
    "CMakeLists.txt": "cmake",
}

# Extension-to-type map derived from the glob configuration. This is used by the
# meta-rule to understand which file suffixes are expected.
EXTENSION_TO_TYPE: Dict[str, str] = {}
for group, patterns in FILE_GLOBS.items():
    for pattern in patterns:
        suffix = Path(pattern.split("*")[-1]).suffix
        if suffix:
            EXTENSION_TO_TYPE.setdefault(suffix.lower(), group)

KNOWN_FILE_TYPES: Set[str] = set(FILE_GLOBS)
KNOWN_FILE_TYPES.update(SPECIAL_FILENAMES.values())


def flatten_globs() -> List[str]:
    """Return a deterministic list of the configured glob patterns."""
    flattened: List[str] = []
    for _, patterns in sorted(FILE_GLOBS.items()):
        flattened.extend(patterns)
    # Include explicit filenames to ensure they are scanned.
    flattened.extend(sorted(SPECIAL_FILENAMES))
    # Remove duplicates while preserving order.
    seen: Set[str] = set()
    ordered: List[str] = []
    for pattern in flattened:
        if pattern not in seen:
            ordered.append(pattern)
            seen.add(pattern)
    return ordered


ALL_PATTERNS: List[str] = flatten_globs()


@dataclass(frozen=True)
class DiscoveryResult:
    """Summary of the scan performed by the engine."""

    files: List[str]
    matched_suffixes: Set[str]
    unmatched_suffixes: Set[str]
    discovered_special: Set[str]

