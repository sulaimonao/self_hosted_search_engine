from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from .engine import (
    RUN_DIR,
    LOGS_DIR,
    SHOT_DIR,
    expand_manifest,
    load_manifest,
    run_all,
    run_probe,
    save_manifest,
)


def list_probes() -> Dict[str, Any]:
    manifest = expand_manifest(load_manifest())
    save_manifest(manifest)
    return {"probes": manifest.get("probes", [])}


def run(labels: Optional[List[str]] = None) -> Dict[str, Any]:
    if labels:
        manifest = expand_manifest(load_manifest())
        selected = [probe for probe in manifest.get("probes", []) if probe.get("label") in labels]
        steps: List[Dict[str, Any]] = []
        errors: List[Dict[str, Any]] = []
        for probe in selected:
            result = run_probe(probe)
            steps.append(result)
            if result.get("status") == "error":
                errors.append(result)
        results = {"steps": steps, "errors": errors}
        (RUN_DIR / "checks.json").write_text(json.dumps(results, indent=2))
        return {
            "results": results,
            "exit_code": 0 if not errors else 1,
            "run_dir": str(RUN_DIR),
        }
    results, exit_code = run_all()
    return {"results": results, "exit_code": exit_code, "run_dir": str(RUN_DIR)}


def artifacts() -> Dict[str, Any]:
    screenshots = [str(path) for path in SHOT_DIR.glob("*.png")]
    return {
        "run_dir": str(RUN_DIR),
        "summary_txt": str(RUN_DIR / "summary.txt"),
        "summary_md": str(RUN_DIR / "summary.md"),
        "checks_json": str(RUN_DIR / "checks.json"),
        "logs_dir": str(LOGS_DIR),
        "screenshots": screenshots,
    }


def start_services() -> Dict[str, Any]:
    results, exit_code = run_all()
    return {"ensured": True, "exit_code": exit_code, "run_dir": str(RUN_DIR)}


def stop_services() -> Dict[str, Any]:
    return {"message": "spawned processes terminate on exit (atexit in engine)"}


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(prog="repo_diag")
    subparsers = parser.add_subparsers(dest="cmd", required=True)
    subparsers.add_parser("list")
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--labels", nargs="*")
    subparsers.add_parser("artifacts")
    subparsers.add_parser("start")
    subparsers.add_parser("stop")
    args = parser.parse_args()

    if args.cmd == "list":
        print(json.dumps(list_probes(), indent=2))
        sys.exit(0)
    if args.cmd == "run":
        output = run(args.labels)
        print(json.dumps(output, indent=2))
        sys.exit(output["exit_code"])
    if args.cmd == "artifacts":
        print(json.dumps(artifacts(), indent=2))
        sys.exit(0)
    if args.cmd == "start":
        output = start_services()
        print(json.dumps(output, indent=2))
        sys.exit(output["exit_code"])
    if args.cmd == "stop":
        print(json.dumps(stop_services(), indent=2))
        sys.exit(0)
