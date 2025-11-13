"""Diagnostics engine orchestrating the self-upgrading rule registry."""

from __future__ import annotations

import argparse
from collections import defaultdict
import fnmatch
import hashlib
import json
import os
import shutil
import textwrap
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    Iterator,
    List,
    Optional,
    Sequence,
    Set,
    Tuple,
)

import yaml

from .globs import ALL_PATTERNS, DiscoveryResult, EXCLUDE_DIRS, SPECIAL_FILENAMES

SCHEMA_VERSION = "1.0.0"
RUN_DIR_NAME = Path("diagnostics") / "run_latest"
BASELINE_DEFAULT = Path("diagnostics") / "baseline.json"
SUPPRESSED_RULES_PATH = Path("tools/diag/SUPPRESSED_RULES.yml")


class Severity(str, Enum):
    """Severity levels used across diagnostics."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

    @property
    def rank(self) -> int:
        if self is Severity.LOW:
            return 1
        if self is Severity.MEDIUM:
            return 2
        return 3


class ExitCode(Enum):
    OK = 0
    WARN = 1
    ERROR = 2
    TOOL_FAILURE = 3


@dataclass
class Finding:
    """Single diagnostic finding emitted by a rule."""

    id: str
    rule_id: str
    severity: Severity
    summary: str
    suggestion: str
    file: Optional[str] = None
    line_hint: Optional[int] = None
    evidence: Optional[str] = None
    doc: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "rule_id": self.rule_id,
            "severity": self.severity.value,
            "summary": self.summary,
            "suggestion": self.suggestion,
            "file": self.file,
            "line_hint": self.line_hint,
            "evidence": self.evidence,
            "doc": self.doc,
            "fingerprint": self.fingerprint,
        }

    @property
    def fingerprint(self) -> str:
        seed = "|".join(
            [
                self.rule_id,
                self.summary,
                self.suggestion,
                self.file or "",
                str(self.line_hint or ""),
            ]
        )
        return hashlib.sha1(seed.encode("utf-8")).hexdigest()


@dataclass
class Rule:
    id: str
    description: str
    severity: Severity
    check: Callable[["RuleContext"], Iterable[Finding]]
    smoke_only: bool = False
    doc: Optional[str] = None


_RULES: Dict[str, Rule] = {}


def register(
    rule_id: str,
    *,
    description: str,
    severity: Severity,
    smoke_only: bool = False,
    doc: Optional[str] = None,
) -> Callable[
    [Callable[["RuleContext"], Iterable[Finding]]],
    Callable[["RuleContext"], Iterable[Finding]],
]:
    """Register a rule with the diagnostics engine."""

    def decorator(func: Callable[["RuleContext"], Iterable[Finding]]):
        if rule_id in _RULES:
            raise ValueError(f"Rule '{rule_id}' already registered")
        _RULES[rule_id] = Rule(
            id=rule_id,
            description=description,
            severity=severity,
            check=func,
            smoke_only=smoke_only,
            doc=doc,
        )
        return func

    return decorator


def iter_rules() -> Iterator[Rule]:
    for rule_id in sorted(_RULES):
        yield _RULES[rule_id]


@dataclass
class SuppressionEntry:
    rule_id: str
    patterns: Tuple[str, ...] = ()
    lines: Tuple[int, ...] = ()
    reason: Optional[str] = None

    def matches(self, finding: Finding) -> bool:
        if self.rule_id != finding.rule_id:
            return False
        if self.patterns and not finding.file:
            return False
        if self.patterns and finding.file:
            relative = finding.file
            if not any(fnmatch.fnmatch(relative, pattern) for pattern in self.patterns):
                return False
        if self.lines and finding.line_hint is not None:
            return finding.line_hint in self.lines
        if self.lines and finding.line_hint is None:
            return False
        return True


class SuppressionIndex:
    """Handle suppressed rules defined in files and SUPPRESSED_RULES.yml."""

    def __init__(self, root: Path, context: "RuleContext") -> None:
        self.root = root
        self.context = context
        self.entries: List[SuppressionEntry] = self._load_entries()
        self.inline_cache: Dict[str, Dict[int, Set[str]]] = {}

    def _load_entries(self) -> List[SuppressionEntry]:
        path = self.root / SUPPRESSED_RULES_PATH
        if not path.exists():
            return []
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
        entries: List[SuppressionEntry] = []
        if isinstance(data, dict):
            data = [data]
        for raw in data:
            if not isinstance(raw, dict):
                continue
            rule_id = str(raw.get("rule") or raw.get("rule_id") or "").strip()
            if not rule_id:
                continue
            patterns = tuple(str(p) for p in raw.get("paths", []) if isinstance(p, str))
            lines = tuple(
                int(line_no)
                for line_no in raw.get("lines", [])
                if isinstance(line_no, int)
            )
            reason = str(raw.get("reason")) if raw.get("reason") else None
            entries.append(
                SuppressionEntry(
                    rule_id=rule_id, patterns=patterns, lines=lines, reason=reason
                )
            )
        return entries

    def _inline_for(self, relative_path: str) -> Dict[int, Set[str]]:
        cached = self.inline_cache.get(relative_path)
        if cached:
            return cached
        text = self.context.read_text(relative_path)
        suppressions: Dict[int, Set[str]] = defaultdict(set)
        if not text:
            self.inline_cache[relative_path] = suppressions
            return suppressions
        for idx, line in enumerate(text.splitlines(), start=1):
            marker_index = line.find("diag:")
            if marker_index == -1:
                continue
            fragment = line[marker_index:]
            lowered = fragment.lower()
            if "disable" not in lowered:
                continue
            rule_part = fragment.split("=", 1)
            if len(rule_part) != 2:
                continue
            raw_rules = rule_part[1]
            # Stop at comment endings to avoid parsing trailing code.
            raw_rules = raw_rules.split("/*")[0]
            raw_rules = raw_rules.split("--")[0]
            raw_rules = raw_rules.split("#")[0]
            identifiers = [piece.strip().strip(",") for piece in raw_rules.split(",")]
            identifiers = [identifier for identifier in identifiers if identifier]
            for identifier in identifiers:
                suppressions[idx].add(identifier)
        self.inline_cache[relative_path] = suppressions
        return suppressions

    def is_suppressed(self, finding: Finding) -> bool:
        for entry in self.entries:
            if entry.matches(finding):
                return True
        if finding.file:
            inline = self._inline_for(finding.file)
            if finding.line_hint is not None:
                if finding.rule_id in inline.get(finding.line_hint, set()):
                    return True
        return False


@dataclass
class Baseline:
    fingerprints: Set[Tuple[str, str]] = field(default_factory=set)

    @classmethod
    def load(cls, path: Path) -> "Baseline":
        if not path.exists():
            return cls()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return cls()
        fingerprints: Set[Tuple[str, str]] = set()
        for item in payload.get("findings", []):
            if not isinstance(item, dict):
                continue
            rule_id = item.get("rule_id") or item.get("rule")
            fingerprint = item.get("fingerprint")
            if isinstance(rule_id, str) and isinstance(fingerprint, str):
                fingerprints.add((rule_id, fingerprint))
        return cls(fingerprints=fingerprints)

    def contains(self, finding: Finding) -> bool:
        return (finding.rule_id, finding.fingerprint) in self.fingerprints


@dataclass
class Results:
    findings: List[Finding] = field(default_factory=list)
    suppressed: List[Finding] = field(default_factory=list)
    baseline_ignored: List[Finding] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def add(self, finding: Finding) -> None:
        self.findings.append(finding)

    def add_suppressed(self, finding: Finding) -> None:
        self.suppressed.append(finding)

    def add_baseline(self, finding: Finding) -> None:
        self.baseline_ignored.append(finding)

    def counts_by_severity(self) -> Dict[Severity, int]:
        counts: Dict[Severity, int] = {severity: 0 for severity in Severity}
        for finding in self.findings:
            counts[finding.severity] += 1
        return counts

    def highest_severity(self) -> Optional[Severity]:
        highest: Optional[Severity] = None
        for finding in self.findings:
            if not highest or finding.severity.rank > highest.rank:
                highest = finding.severity
        return highest

    def as_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "summary": {
                "counts": {
                    severity.value: count
                    for severity, count in self.counts_by_severity().items()
                },
                "suppressed": len(self.suppressed),
                "baseline": len(self.baseline_ignored),
                "errors": len(self.errors),
            },
            "findings": [finding.to_dict() for finding in self.findings],
            "suppressed_findings": [finding.to_dict() for finding in self.suppressed],
            "baseline_findings": [
                finding.to_dict() for finding in self.baseline_ignored
            ],
            "errors": self.errors,
        }

    def to_text(self) -> str:
        counts = self.counts_by_severity()
        summary_lines = [
            "Diagnostics summary:",
            f"  High: {counts[Severity.HIGH]}",
            f"  Medium: {counts[Severity.MEDIUM]}",
            f"  Low: {counts[Severity.LOW]}",
            f"  Suppressed: {len(self.suppressed)}",
            f"  Baseline: {len(self.baseline_ignored)}",
        ]
        if self.errors:
            summary_lines.append(f"  Errors: {len(self.errors)}")
        detail_lines: List[str] = []
        for finding in self.findings:
            location = f" ({finding.file}:{finding.line_hint})" if finding.file else ""
            detail_lines.append(
                f"[{finding.rule_id}][{finding.severity.value}] {finding.summary}{location}"
            )
            detail_lines.append(f"    Suggestion: {finding.suggestion}")
            if finding.evidence:
                detail_lines.append(f"    Evidence: {finding.evidence}")
        body = "\n".join(detail_lines) if detail_lines else "No actionable findings."
        return "\n".join(summary_lines + ["", body])

    def to_markdown(self) -> str:
        counts = self.counts_by_severity()
        header = textwrap.dedent(
            f"""
            # Diagnostics Report

            | Severity | Count |
            | --- | ---: |
            | High | {counts[Severity.HIGH]} |
            | Medium | {counts[Severity.MEDIUM]} |
            | Low | {counts[Severity.LOW]} |
            | Suppressed | {len(self.suppressed)} |
            | Baseline | {len(self.baseline_ignored)} |
            """
        ).strip()
        lines = [header, ""]
        if self.errors:
            lines.append("## Errors")
            for error in self.errors:
                lines.append(f"- {error}")
            lines.append("")
        if self.findings:
            lines.append("## Findings")
            for finding in self.findings:
                location = (
                    f" (`{finding.file}` line {finding.line_hint})"
                    if finding.file
                    else ""
                )
                lines.append(
                    f"- **{finding.rule_id}** ({finding.severity.value}){location}: {finding.summary}"
                )
                lines.append(f"  - Suggestion: {finding.suggestion}")
                if finding.evidence:
                    lines.append(f"  - Evidence: `{finding.evidence}`")
        else:
            lines.append("No actionable findings.")
        return "\n".join(lines)


class RuleContext:
    """Expose repository information to rules."""

    def __init__(
        self,
        root: Path,
        discovery: DiscoveryResult,
        *,
        smoke: bool,
        scope: Optional[Set[str]] = None,
    ) -> None:
        self.root = root
        self.discovery = discovery
        self.smoke = smoke
        self.scope = set(scope) if scope else None
        self._text_cache: Dict[str, str] = {}

    def resolve(self, relative_path: str) -> Path:
        return self.root / relative_path

    def read_text(self, relative_path: str) -> str:
        if relative_path in self._text_cache:
            return self._text_cache[relative_path]
        try:
            text = (self.root / relative_path).read_text(encoding="utf-8")
        except FileNotFoundError:
            text = ""
        self._text_cache[relative_path] = text
        return text

    def iter_files(self, *suffixes: str) -> Iterator[str]:
        for relative in self.discovery.files:
            if suffixes and not any(relative.endswith(suffix) for suffix in suffixes):
                continue
            yield relative

    def iter_patterns(self, *patterns: str) -> Iterator[str]:
        for relative in self.discovery.files:
            if patterns and not any(
                fnmatch.fnmatch(relative, pattern) for pattern in patterns
            ):
                continue
            yield relative

    @property
    def matched_suffixes(self) -> Set[str]:
        return set(self.discovery.matched_suffixes)

    @property
    def unmatched_suffixes(self) -> Set[str]:
        return set(self.discovery.unmatched_suffixes)

    @property
    def discovered_special(self) -> Set[str]:
        return self.discovery.discovered_special


def _matches_patterns(relative_path: str, patterns: Sequence[str]) -> bool:
    alt_path = f"./{relative_path}"
    return any(
        fnmatch.fnmatch(relative_path, pattern) or fnmatch.fnmatch(alt_path, pattern)
        for pattern in patterns
    )


def _discover_files(root: Path, scope: Optional[Set[str]] = None) -> DiscoveryResult:
    files: List[str] = []
    matched_suffixes: Set[str] = set()
    unmatched_suffixes: Set[str] = set()
    special: Set[str] = set()
    patterns = ALL_PATTERNS
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in EXCLUDE_DIRS]
        for filename in filenames:
            full_path = Path(dirpath) / filename
            relative = full_path.relative_to(root)
            relative_posix = relative.as_posix()
            if scope is not None and relative_posix not in scope:
                continue
            matched = _matches_patterns(relative_posix, patterns)
            if matched:
                files.append(relative_posix)
            suffix = full_path.suffix.lower()
            if suffix:
                if matched:
                    matched_suffixes.add(suffix)
                else:
                    unmatched_suffixes.add(suffix)
            if filename in SPECIAL_FILENAMES:
                special.add(filename)
    files.sort()
    return DiscoveryResult(
        files=files,
        matched_suffixes=matched_suffixes,
        unmatched_suffixes=unmatched_suffixes,
        discovered_special=special,
    )


class DiagnosticsEngine:
    """Run the registered rules and produce artefacts."""

    def __init__(self, root: Optional[Path] = None) -> None:
        self.root = root or Path.cwd()

    def run(
        self,
        *,
        smoke: bool = False,
        fail_on: Severity = Severity.HIGH,
        only: Optional[Set[str]] = None,
        skip: Optional[Set[str]] = None,
        baseline_path: Optional[Path] = None,
        write_artifacts: bool = True,
        scope: Optional[Set[str]] = None,
    ) -> Tuple[Results, ExitCode, Dict[str, str]]:
        discovery = _discover_files(self.root, scope)
        context = RuleContext(self.root, discovery, smoke=smoke, scope=scope)
        suppression_index = SuppressionIndex(self.root, context)
        baseline = Baseline.load(self.root / (baseline_path or BASELINE_DEFAULT))
        results = Results()

        artefacts: Dict[str, str] = {}

        def _flush_artifacts() -> None:
            nonlocal artefacts
            if write_artifacts:
                artefacts = self._write_artifacts(results)

        if write_artifacts:
            artefacts = self._write_artifacts(results)

        from .probes import iter_probes  # Local import to avoid circular dependency

        probes = list(iter_probes())
        probe_ids = {probe.id for probe in probes}

        def _record_findings(findings: Iterable[Finding]) -> None:
            for finding in findings:
                if suppression_index.is_suppressed(finding):
                    results.add_suppressed(finding)
                    continue
                if baseline.contains(finding):
                    results.add_baseline(finding)
                    continue
                results.add(finding)

        for probe in probes:
            if only and probe.id not in only:
                continue
            if skip and probe.id in skip:
                continue
            try:
                findings = list(probe.check(context))
            except Exception as exc:  # pragma: no cover - protective guard
                results.errors.append(f"{probe.id}: {exc}")
                _flush_artifacts()
                continue
            _record_findings(findings)
            _flush_artifacts()

        for rule in iter_rules():
            if rule.id in probe_ids:
                continue
            if only and rule.id not in only:
                continue
            if skip and rule.id in skip:
                continue
            if rule.smoke_only and not smoke:
                continue
            try:
                findings = list(rule.check(context))
            except Exception as exc:  # pragma: no cover - protective guard
                results.errors.append(f"{rule.id}: {exc}")
                _flush_artifacts()
                continue
            _record_findings(findings)
            _flush_artifacts()

        exit_code = self._compute_exit_code(results, fail_on)
        if write_artifacts:
            artefacts = self._write_artifacts(results)
        return results, exit_code, artefacts

    def _compute_exit_code(self, results: Results, fail_on: Severity) -> ExitCode:
        if results.errors:
            return ExitCode.TOOL_FAILURE
        highest = results.highest_severity()
        if highest is None:
            return ExitCode.OK
        if highest.rank >= fail_on.rank:
            return ExitCode.ERROR
        return ExitCode.OK

    def _write_artifacts(self, results: Results) -> Dict[str, str]:
        run_dir = self.root / RUN_DIR_NAME
        shutil.rmtree(run_dir, ignore_errors=True)
        run_dir.mkdir(parents=True, exist_ok=True)
        generated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        payload = results.as_dict()
        payload.update(
            {
                "generated_at": generated_at,
                "schema_version": SCHEMA_VERSION,
            }
        )
        summary_txt = results.to_text()
        summary_md = results.to_markdown()
        checks_json = json.dumps(payload, indent=2)
        (run_dir / "checks.json").write_text(checks_json, encoding="utf-8")
        (run_dir / "summary.txt").write_text(summary_txt, encoding="utf-8")
        (run_dir / "summary.md").write_text(summary_md, encoding="utf-8")
        sarif_payload = self._build_sarif(results, generated_at)
        sarif_json = json.dumps(sarif_payload, indent=2)
        (run_dir / "checks.sarif").write_text(sarif_json, encoding="utf-8")
        return {
            "checks.json": checks_json,
            "summary.txt": summary_txt,
            "summary.md": summary_md,
            "checks.sarif": sarif_json,
        }

    def _build_sarif(self, results: Results, generated_at: str) -> Dict[str, Any]:
        rules = []
        for rule in iter_rules():
            rules.append(
                {
                    "id": rule.id,
                    "name": rule.description,
                    "shortDescription": {"text": rule.description},
                    "properties": {"severity": rule.severity.value},
                }
            )
        sarif_results = []
        for finding in results.findings:
            sarif_results.append(
                {
                    "ruleId": finding.rule_id,
                    "level": finding.severity.value,
                    "message": {"text": finding.summary},
                    "locations": (
                        [
                            {
                                "physicalLocation": {
                                    "artifactLocation": {"uri": finding.file},
                                    "region": {"startLine": finding.line_hint},
                                }
                            }
                        ]
                        if finding.file
                        else []
                    ),
                    "properties": {
                        "suggestion": finding.suggestion,
                        "evidence": finding.evidence,
                        "fingerprint": finding.fingerprint,
                    },
                }
            )
        return {
            "version": "2.1.0",
            "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
            "runs": [
                {
                    "tool": {
                        "driver": {
                            "name": "self_hosted_search_engine-diagnostics",
                            "informationUri": "https://github.com/self_hosted_search_engine",
                            "semanticVersion": SCHEMA_VERSION,
                            "rules": rules,
                        }
                    },
                    "results": sarif_results,
                    "invocations": [
                        {
                            "executionSuccessful": True,
                            "endTimeUtc": generated_at,
                        }
                    ],
                }
            ],
        }


def parse_fail_on(value: str) -> Severity:
    try:
        return Severity(value)
    except ValueError as exc:  # pragma: no cover - CLI validation safety net
        raise argparse.ArgumentTypeError(f"Unknown severity level: {value}") from exc
