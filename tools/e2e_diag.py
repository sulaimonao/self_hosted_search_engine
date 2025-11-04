"""CLI entry point for repository diagnostics."""
from __future__ import annotations

import argparse
import contextlib
import fnmatch
import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Dict, Iterable, Optional, Set

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.diag import DiagnosticsEngine, ExitCode, Severity, parse_fail_on
from tools.diag.autofix_env import apply_autofix as apply_env_autofix
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
    scope: Optional[Set[str]],
) -> ExitCode:
    results, exit_code, artefacts = engine.run(
        smoke=smoke,
        fail_on=fail_on,
        only=only,
        skip=skip,
        baseline_path=baseline,
        write_artifacts=True,
        scope=scope,
    )
    payload = results.as_dict()
    print(_render_output(output_format, artefacts, payload))
    if results.errors:
        for error in results.errors:
            print(f"[diag:error] {error}", file=sys.stderr)
    return exit_code


def _exit_status(code: ExitCode) -> int:
    if code is ExitCode.TOOL_FAILURE:
        return 2
    if code is ExitCode.ERROR:
        return 1
    return 0


class DiagnosticsTimeout(RuntimeError):
    """Raised when the diagnostics exceed the configured timeout."""


@contextlib.contextmanager
def _enforce_timeout(seconds: Optional[int]) -> None:
    if not seconds:
        yield
        return

    triggered = {"value": False}

    def _handle_alarm(signum: int, frame: object) -> None:  # pragma: no cover - signal path
        raise DiagnosticsTimeout(f"Diagnostics timed out after {seconds} seconds")

    if hasattr(signal, "SIGALRM"):
        previous = signal.getsignal(signal.SIGALRM)
        signal.signal(signal.SIGALRM, _handle_alarm)
        signal.alarm(seconds)
        try:
            yield
        finally:  # pragma: no cover - signal cleanup
            signal.alarm(0)
            signal.signal(signal.SIGALRM, previous)
    else:  # pragma: no cover - non-POSIX fallback
        def _interrupt() -> None:
            triggered["value"] = True
            threading.interrupt_main()

        timer = threading.Timer(seconds, _interrupt)
        timer.daemon = True
        timer.start()
        try:
            try:
                yield
            except KeyboardInterrupt:
                if triggered["value"]:
                    raise DiagnosticsTimeout(
                        f"Diagnostics timed out after {seconds} seconds"
                    ) from None
                raise
        finally:
            timer.cancel()


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _parse_since_scope(root: Path, value: str) -> Set[str]:
    ref_check = _git(root, "rev-parse", "--verify", value)
    changed: Set[str] = set()
    if ref_check.returncode == 0:
        diff = _git(root, "diff", "--name-only", f"{value}..HEAD")
        if diff.returncode != 0:
            raise RuntimeError(diff.stderr.strip() or f"Failed to diff against {value}")
        changed.update(_normalise_paths(diff.stdout.splitlines()))
    else:
        log = _git(root, "log", "--since", value, "--format=", "--name-only", "HEAD")
        if log.returncode != 0:
            raise RuntimeError(log.stderr.strip() or f"Failed to resolve since={value}")
        changed.update(_normalise_paths(log.stdout.splitlines()))

    status = _git(root, "status", "--porcelain", "--untracked-files=all")
    if status.returncode == 0:
        for line in status.stdout.splitlines():
            if len(line) < 4:
                continue
            path = line[3:]
            if " -> " in path:
                path = path.split(" -> ", 1)[1]
            changed.add(Path(path).as_posix())

    return {path for path in changed if path}


def _normalise_paths(lines: Iterable[str]) -> Set[str]:
    paths: Set[str] = set()
    for line in lines:
        line = line.strip()
        if not line:
            continue
        paths.add(Path(line).as_posix())
    return paths


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
    parser.add_argument(
        "--autofix",
        action="store_true",
        help="Apply safe autofixes before running diagnostics",
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
    parser.add_argument(
        "--since",
        help="Limit diagnostics to files changed since a commit/ref or timestamp",
    )
    args = parser.parse_args(argv)

    only = set(filter(None, (args.only or "").split(","))) if args.only else None
    skip = set(filter(None, (args.skip or "").split(","))) if args.skip else None

    scope: Optional[Set[str]] = None
    if args.since:
        try:
            scope = _parse_since_scope(Path.cwd(), args.since)
        except RuntimeError as exc:
            print(f"[diag:error] {exc}", file=sys.stderr)
            return 2
        if not scope:
            print("[diag] No files changed since the provided reference; exiting early.")
            return 0

    if args.autofix:
        entries = apply_env_autofix(Path.cwd())
        print("### Autofix: environment examples")
        if entries:
            for entry in entries:
                target = entry.target.resolve()
                try:
                    target_relative = target.relative_to(Path.cwd())
                except ValueError:
                    target_relative = target
                refs = ", ".join(entry.references) if entry.references else "unknown reference"
                print(f"- `{entry.key}` → `{target_relative}` (refs: {refs})")
        else:
            print("- No missing environment keys detected.")

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
            scope=scope,
        )

    timeout_value = os.getenv("DIAG_TIMEOUT")
    timeout_seconds: Optional[int] = None
    if timeout_value:
        try:
            timeout_seconds = int(timeout_value)
        except ValueError:
            print(
                f"[diag:error] Invalid DIAG_TIMEOUT '{timeout_value}'; expected integer seconds.",
                file=sys.stderr,
            )
            return 2

    try:
        with _enforce_timeout(timeout_seconds):
            exit_code = execute()
    except DiagnosticsTimeout as exc:
        print(f"[diag:error] {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # pragma: no cover - defensive guard
        print(f"[diag:error] Unexpected failure: {exc}", file=sys.stderr)
        return 2

    if not args.watch:
        return _exit_status(exit_code)

    try:
        previous_mtimes = _collect_mtimes(Path.cwd())
        while True:
            time.sleep(1.0)
            current_mtimes = _collect_mtimes(Path.cwd())
            if current_mtimes != previous_mtimes:
                print("\n[diag] Change detected; re-running diagnostics...", file=sys.stderr)
                try:
                    with _enforce_timeout(timeout_seconds):
                        exit_code = execute()
                except DiagnosticsTimeout as exc:
                    print(f"[diag:error] {exc}", file=sys.stderr)
                    return 2
                except Exception as exc:  # pragma: no cover - defensive guard
                    print(f"[diag:error] Unexpected failure: {exc}", file=sys.stderr)
                    return 2
                previous_mtimes = current_mtimes
    except KeyboardInterrupt:
        print("\n[diag] Watch mode interrupted", file=sys.stderr)
    return _exit_status(exit_code)


if __name__ == "__main__":
    raise SystemExit(main())
