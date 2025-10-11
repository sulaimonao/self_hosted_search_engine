"""System check endpoint combining backend and diagnostics health signals."""

from __future__ import annotations

import os
import socket
import time
from typing import Any

from flask import Blueprint, current_app, jsonify

from ..config import AppConfig
from ..jobs.diagnostics import run_diagnostics
from ..jobs.runner import JobRunner

bp = Blueprint("system_check_api", __name__, url_prefix="/api")


def _path_check(label: str, path_str: str, *, critical: bool = True) -> dict[str, Any]:
    exists = False
    try:
        exists = os.path.exists(path_str)
    except OSError:
        exists = False
    status = "pass" if exists else "fail"
    detail = None if exists else f"Missing path: {path_str}"
    return {
        "id": label,
        "title": label,
        "status": status,
        "detail": detail,
        "critical": critical,
    }


def _port_check(port: int) -> dict[str, Any]:
    start = time.perf_counter()
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            duration_ms = int((time.perf_counter() - start) * 1000)
            return {
                "id": "backend-port",
                "title": f"Backend port {port} reachable",
                "status": "pass",
                "detail": None,
                "critical": True,
                "duration_ms": duration_ms,
            }
    except OSError as exc:
        duration_ms = int((time.perf_counter() - start) * 1000)
        return {
            "id": "backend-port",
            "title": f"Backend port {port} reachable",
            "status": "fail",
            "detail": str(exc),
            "critical": True,
            "duration_ms": duration_ms,
        }


def _aggregate_status(checks: list[dict[str, Any]]) -> tuple[str, bool]:
    summary_status = "pass"
    critical_failed = False
    for entry in checks:
        status = entry.get("status", "unknown")
        if status == "pass":
            continue
        if entry.get("critical"):
            summary_status = "fail"
            critical_failed = True
            break
        if summary_status == "pass":
            summary_status = status
    return summary_status, critical_failed


def _run_diagnostics_light(config: AppConfig, runner: JobRunner) -> dict[str, Any]:
    started = time.perf_counter()
    job_id = runner.submit(lambda: run_diagnostics(config, include_pytest=False))
    timeout_seconds = float(os.getenv("SYSTEM_CHECK_DIAGNOSTICS_TIMEOUT", "45"))
    timeout_seconds = max(5.0, min(timeout_seconds, 180.0))
    deadline = time.perf_counter() + timeout_seconds
    poll_interval = 0.5
    state = "queued"
    result: dict[str, Any] | None = None
    error: str | None = None
    while time.perf_counter() < deadline:
        snapshot = runner.status(job_id)
        state = str(snapshot.get("state") or "unknown").lower()
        if state == "done":
            result = snapshot.get("result") if isinstance(snapshot.get("result"), dict) else None
            break
        if state == "error":
            error = str(snapshot.get("error") or "diagnostics job failed")
            break
        time.sleep(poll_interval)
    else:
        state = "timeout"

    duration_ms = int((time.perf_counter() - started) * 1000)
    payload: dict[str, Any] = {
        "job_id": job_id,
        "duration_ms": duration_ms,
        "status": "pass",
        "result": result,
    }
    if state == "done":
        payload["status"] = "pass"
    elif state == "timeout":
        payload["status"] = "timeout"
        payload["detail"] = f"Diagnostics job exceeded {int(timeout_seconds)}s window"
    elif state == "error":
        payload["status"] = "fail"
        payload["detail"] = error or "Diagnostics job failed"
    else:
        payload["status"] = state
    return payload


def _check_llm() -> dict[str, Any]:
    config: AppConfig = current_app.config["APP_CONFIG"]
    target = (config.ollama_url or "").strip()
    if not target:
        return {
            "status": "skip",
            "reachable": False,
            "detail": "Ollama host not configured",
            "critical": False,
        }
    started = time.perf_counter()
    with current_app.test_client() as client:
        response = client.get("/api/llm/health")
    duration_ms = int((time.perf_counter() - started) * 1000)
    payload = response.get_json(silent=True) or {}
    reachable = bool(payload.get("reachable"))
    status = "pass" if reachable else "warn"
    detail = None
    if not reachable:
        detail = "Ollama host unreachable"
    return {
        "status": status,
        "reachable": reachable,
        "detail": detail,
        "critical": False,
        "duration_ms": duration_ms,
        "payload": payload,
    }


def _enqueue_warmup(runner: JobRunner) -> str | None:
    config: AppConfig = current_app.config["APP_CONFIG"]
    ollama_url = (config.ollama_url or "").strip()

    def _job() -> dict[str, Any]:
        summary: dict[str, Any] = {
            "generated_at": time.time(),
            "ollama_url": ollama_url or None,
        }
        if ollama_url:
            try:
                import requests

                response = requests.get(ollama_url, timeout=3)
            except Exception as exc:  # pragma: no cover - best effort
                summary["ollama_error"] = str(exc)
            else:
                summary["ollama_status_code"] = response.status_code
        return summary

    try:
        return runner.submit(_job)
    except Exception:  # pragma: no cover - defensive
        return None


@bp.post("/system_check")
def run_system_check():
    config: AppConfig = current_app.config["APP_CONFIG"]
    runner: JobRunner = current_app.config["JOB_RUNNER"]

    backend_checks: list[dict[str, Any]] = []
    backend_checks.append(_path_check("data-directory", str(config.agent_data_dir)))
    backend_checks.append(_path_check("logs-directory", str(config.logs_dir)))
    backend_checks.append(_path_check("index-directory", str(config.index_dir)))
    backend_checks.append(_path_check("frontier-db", str(config.frontier_db_path)))

    port_env = os.getenv("BACKEND_PORT")
    try:
        port = int(port_env) if port_env else 5050
    except ValueError:
        port = 5050
    backend_checks.append(_port_check(port))

    backend_status, backend_critical = _aggregate_status(backend_checks)

    diagnostics = _run_diagnostics_light(config, runner)
    diag_status = diagnostics.get("status")
    diag_critical = diag_status in {"fail", "timeout"}

    llm = _check_llm()
    llm_critical = bool(llm.get("critical")) and llm.get("status") not in {"pass", "skip"}

    critical_failures = backend_critical or diag_critical or llm_critical

    warmup_job_id = None
    if not critical_failures:
        warmup_job_id = _enqueue_warmup(runner)

    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "backend": {
            "status": backend_status,
            "checks": backend_checks,
        },
        "diagnostics": diagnostics,
        "llm": llm,
        "summary": {
            "critical_failures": critical_failures,
            "warmup_job_id": warmup_job_id,
        },
    }
    return jsonify(payload)
