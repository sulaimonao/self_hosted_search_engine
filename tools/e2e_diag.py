"""CLI entry point for repository diagnostics."""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, Optional, Set

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.diag import DiagnosticsEngine, ExitCode, Severity, parse_fail_on
from tools.diag.globs import ALL_PATTERNS, EXCLUDE_DIRS


def _collect_mtimes(root: Path) -> Dict[str, float]:
    mtimes: Dict[str, float] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in EXCLUDE_DIRS]
        for filename in filenames:
            relative = Path(dirpath, filename).relative_to(root).as_posix()
            if not ALL_PATTERNS or any(fnmatch.fnmatch(relative, pattern) for pattern in ALL_PATTERNS):
                try:
                    mtimes[relative] = (Path(dirpath) / filename).stat().st_mtime
                except FileNotFoundError:
                    continue
    return mtimes


def _render_output(format_name: str, artefacts: Dict[str, str], results_dict: Dict[str, object]) -> str:
    if format_name == "text":
        return artefacts.get("summary.txt", "")
    if format_name == "md":
        return artefacts.get("summary.md", "")
    if format_name == "json":
        return json.dumps(results_dict, indent=2)
    if format_name == "sarif":
        return artefacts.get("checks.sarif", "")
    raise ValueError(f"Unknown output format: {format_name}")


def run_once(
    engine: DiagnosticsEngine,
    *,
    smoke: bool,
    fail_on: Severity,
    only: Optional[Set[str]],
    skip: Optional[Set[str]],
    baseline: Optional[Path],
    output_format: str,
) -> ExitCode:
    results, exit_code, artefacts = engine.run(
        smoke=smoke,
        fail_on=fail_on,
        only=only,
        skip=skip,
        baseline_path=baseline,
        write_artifacts=True,
    )
    payload = results.as_dict()
    print(_render_output(output_format, artefacts, payload))
    if results.errors:
        for error in results.errors:
            print(f"[diag:error] {error}", file=sys.stderr)
    return exit_code


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run repository diagnostics")
    parser.add_argument("--smoke", action="store_true", help="Enable optional runtime smoke checks")
    parser.add_argument("--watch", action="store_true", help="Re-run diagnostics on file changes")
    parser.add_argument(
        "--fail-on",
        default=Severity.HIGH,
        type=parse_fail_on,
        help="Severity threshold that triggers a non-zero exit (high, medium, low)",
    )
    parser.add_argument("--only", help="Comma separated list of rule IDs to run")
    parser.add_argument("--skip", help="Comma separated list of rule IDs to skip")
    parser.add_argument("--baseline", type=Path, help="Baseline JSON file to ignore historical findings")
    parser.add_argument(
        "--format",
        choices=("text", "md", "json", "sarif"),
        default="text",
        help="Output format printed to stdout",
    )
    args = parser.parse_args(argv)

    only = set(filter(None, (args.only or "").split(","))) if args.only else None
    skip = set(filter(None, (args.skip or "").split(","))) if args.skip else None

    engine = DiagnosticsEngine(Path.cwd())

    def execute() -> ExitCode:
        return run_once(
            engine,
            smoke=args.smoke,
            fail_on=args.fail_on,
            only=only,
            skip=skip,
            baseline=args.baseline,
            output_format=args.format,
        )

    exit_code = execute()
    if not args.watch:
        return exit_code.value

    try:
        previous_mtimes = _collect_mtimes(Path.cwd())
        while True:
            time.sleep(1.0)
            current_mtimes = _collect_mtimes(Path.cwd())
            if current_mtimes != previous_mtimes:
                print("\n[diag] Change detected; re-running diagnostics...", file=sys.stderr)
                exit_code = execute()
                previous_mtimes = current_mtimes
    except KeyboardInterrupt:
        print("\n[diag] Watch mode interrupted", file=sys.stderr)
    return exit_code.value


if __name__ == "__main__":
    raise SystemExit(main())
