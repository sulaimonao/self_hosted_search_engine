"""Diagnostics API for capturing backend and repository health snapshots."""

from __future__ import annotations

import subprocess
import json
from pathlib import Path
from typing import Any

from flask import Blueprint, current_app, g, jsonify, request

from ..config import AppConfig
from ..jobs.diagnostics import run_diagnostics
from ..jobs.runner import JobRunner
from ..services.incident_log import IncidentLog

bp = Blueprint("diagnostics_api", __name__, url_prefix="/api")


@bp.post("/diagnostics")
def diagnostics_endpoint():
    payload = request.get_json(silent=True)
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        return jsonify({"error": "JSON object body required"}), 400

    include_pytest_raw = payload.get("include_pytest")
    include_pytest: bool | None
    if include_pytest_raw is None:
        include_pytest = None
    elif isinstance(include_pytest_raw, bool):
        include_pytest = include_pytest_raw
    else:
        return jsonify({"error": "include_pytest must be a boolean"}), 400

    config: AppConfig = current_app.config["APP_CONFIG"]
    runner: JobRunner = current_app.config["JOB_RUNNER"]

    def _job() -> dict:
        return run_diagnostics(config, include_pytest=include_pytest)

    job_id = runner.submit(_job)
    return jsonify({"job_id": job_id})


@bp.post("/diagnostics/run")
def diagnostics_run():
    project_root = Path(current_app.root_path).resolve().parent.parent
    script_path = project_root / "tools" / "e2e_diag.py"
    if not script_path.exists():
        return jsonify({"ok": False, "error": "script_missing"}), 500

    try:
        result = subprocess.run(
            ["python3", str(script_path)],
            capture_output=True,
            text=True,
            cwd=str(project_root),
            check=False,
        )
    except OSError as exc:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": exc.__class__.__name__,
                    "message": str(exc),
                }
            ),
            500,
        )

    stdout_text = (result.stdout or "").strip()
    summary_text = stdout_text.splitlines()[0] if stdout_text else ""
    checks_payload = None
    try:
        parsed = json.loads(stdout_text) if stdout_text else None
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, dict):
        summary_text = str(parsed.get("summary") or parsed.get("status") or summary_text or "Diagnostics finished")
        raw_checks = parsed.get("checks") or parsed.get("results")
        if isinstance(raw_checks, list):
            checks: list[dict[str, object]] = []
            for entry in raw_checks[:20]:
                if not isinstance(entry, dict):
                    continue
                status_val = str(entry.get("status") or entry.get("state") or "unknown").strip()
                detail_val = entry.get("detail") or entry.get("message") or entry.get("summary")
                checks.append(
                    {
                        "id": str(entry.get("id") or entry.get("name") or f"check_{len(checks)+1}"),
                        "status": status_val or "unknown",
                        "detail": detail_val,
                        "critical": bool(entry.get("critical"))
                        or status_val.lower() in {"fail", "error", "timeout"},
                    }
                )
            if checks:
                checks_payload = checks

    status = "ok" if result.returncode == 0 else "error"
    response_payload: dict[str, Any] = {
        "ok": result.returncode == 0,
        "status": status,
        "summary": summary_text or ("Diagnostics completed" if result.returncode == 0 else "Diagnostics reported issues"),
        "checks": checks_payload,
        "traceId": getattr(g, "trace_id", None),
        "returncode": result.returncode,
        "stdout": stdout_text,
        "stderr": (result.stderr or "").strip(),
    }
    incident_log = current_app.config.get("INCIDENT_LOG")
    if isinstance(incident_log, IncidentLog):
        response_payload["incidents"] = incident_log.list(limit=50)
        response_payload["incident_snapshot"] = incident_log.snapshot()
    return jsonify(response_payload)
