#!/usr/bin/env python3
from __future__ import annotations

import atexit
import json
import os
import platform
import re
import socket
import time
import signal
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

API_PORT = int(os.environ.get("BACKEND_PORT", "5050"))
WEB_PORT = int(os.environ.get("PORT", "3100"))
API_BASE = f"http://127.0.0.1:{API_PORT}"
RENDERER = f"http://localhost:{WEB_PORT}"

DEFAULT_TIMEOUT = (5, 10)  # (connect, read)
RUN_DIR = Path.cwd() / "diagnostics" / time.strftime("run_%Y%m%d-%H%M%S")
LOGS_DIR = RUN_DIR / "logs"
SHOT_DIR = RUN_DIR / "screenshots"
MANIFEST_PATH = Path("tools/diag/manifest.json")
API_CMD = [
    "bash",
    "-lc",
    f"make api || (PYTHONPATH=. BACKEND_PORT={API_PORT} python3 -m backend.app)",
]
WEB_CMD = ["bash", "-lc", "npm --prefix frontend run dev:web"]
WEB_ENV = {
    "PORT": str(WEB_PORT),
    "NEXT_PUBLIC_API_BASE_URL": f"http://127.0.0.1:{API_PORT}",
}

PROCS: List[Tuple[Any, Any]] = []  # (proc, loghandle)


def _mkdirs() -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    (RUN_DIR / "summary.txt").touch()
    for name in ("api.log", "web.log", "browser-console.jsonl", "browser-network.jsonl"):
        (LOGS_DIR / name).touch()


def _start(cmd: List[str], log_path: Path, extra_env: Optional[Dict[str, str]] = None):
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    lf = open(log_path, "w", encoding="utf-8")
    popen_args: Dict[str, Any] = {
        "cwd": Path.cwd(),
        "env": env,
        "stdout": lf,
        "stderr": subprocess.STDOUT,
        "text": True,
    }
    if os.name == "nt":  # pragma: no cover - windows-specific branch
        popen_args["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    else:
        popen_args["preexec_fn"] = os.setsid  # type: ignore[attr-defined]
    proc = subprocess.Popen(
        cmd,
        **popen_args,
    )
    PROCS.append((proc, lf))
    return proc


def _kill_procs() -> None:
    for proc, lf in PROCS:
        try:
            if proc.poll() is None:
                if os.name == "nt":  # pragma: no cover - windows-specific branch
                    proc.terminate()
                else:
                    os.killpg(proc.pid, signal.SIGTERM)
        except Exception:
            pass
        try:
            lf.close()
        except Exception:
            pass
    time.sleep(1.0)
    for proc, _ in PROCS:
        try:
            if proc.poll() is None:
                if os.name == "nt":  # pragma: no cover - windows-specific branch
                    proc.kill()
                else:
                    os.killpg(proc.pid, signal.SIGKILL)
        except Exception:
            pass


def log(msg: str) -> None:
    print(msg, flush=True)
    with open(RUN_DIR / "summary.txt", "a", encoding="utf-8") as handle:
        handle.write(msg + "\n")


def _port_free(port: int) -> bool:
    sock = socket.socket()
    try:
        return sock.connect_ex(("127.0.0.1", port)) != 0
    finally:
        sock.close()


def _get(url: str, **kwargs):
    return requests.get(url, timeout=kwargs.pop("timeout", DEFAULT_TIMEOUT), **kwargs)


def _post(url: str, **kwargs):
    return requests.post(url, timeout=kwargs.pop("timeout", DEFAULT_TIMEOUT), **kwargs)


def _console_record(msg):
    mtype = msg.type() if callable(getattr(msg, "type", None)) else getattr(msg, "type", None)
    text = msg.text() if callable(getattr(msg, "text", None)) else getattr(msg, "text", None)
    loc = {}
    try:
        loc = msg.location if isinstance(msg.location, dict) else dict(msg.location or {})  # type: ignore[attr-defined]
    except Exception:
        loc = {}
    return {
        "type": mtype,
        "text": text,
        "url": loc.get("url"),
        "line": loc.get("lineNumber"),
        "col": loc.get("columnNumber"),
    }


def _requestfailed_record(req):
    failure_attr = getattr(req, "failure", None)
    try:
        failure = failure_attr() if callable(failure_attr) else failure_attr
    except Exception:
        failure = None
    err_text = failure.get("errorText") if isinstance(failure, dict) else (failure if isinstance(failure, str) else None)
    resource_attr = getattr(req, "resource_type", None)
    resource_type = resource_attr() if callable(resource_attr) else resource_attr
    url = req.url if hasattr(req, "url") else None
    method = req.method if hasattr(req, "method") else None
    return {
        "url": url,
        "method": method,
        "failure": err_text,
        "resourceType": resource_type,
    }


console_path = RUN_DIR / "logs" / "browser-console.jsonl"
net_path = RUN_DIR / "logs" / "browser-network.jsonl"


def _write_jsonl(path: Path, obj: Dict[str, Any]) -> None:
    try:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(obj, ensure_ascii=False) + "\n")
    except Exception:
        pass


# ---------- Detect ----------
def detect_api_routes_runtime() -> List[Dict[str, Any]]:
    try:
        resp = _get(f"{API_BASE}/api/meta/routes")
        if resp.status_code == 200:
            payload = resp.json()
            if isinstance(payload, list):
                return payload
            if isinstance(payload, dict):
                return payload.get("routes", [])
    except Exception:
        pass
    return []


def detect_api_routes_static() -> List[Dict[str, Any]]:
    routes: List[Dict[str, Any]] = []
    for path in Path("backend").rglob("*.py"):
        try:
            text = path.read_text(errors="ignore")
        except Exception:
            continue
        for match in re.finditer(r"@(?:app|[\w_]+)\.route\(\s*['\"]([^'\"]+)['\"].*?\)", text):
            routes.append({"rule": match.group(1)})
    seen: set[str] = set()
    deduped: List[Dict[str, Any]] = []
    for route in routes:
        rule = route.get("rule", "")
        if not rule.startswith("/api/"):
            continue
        if rule in seen:
            continue
        seen.add(rule)
        deduped.append({"rule": rule, "methods": ["GET", "POST"]})
    return deduped


def detect_web_routes() -> List[str]:
    paths: List[str] = []
    page_files = list(Path("frontend/pages").rglob("*.tsx")) + list(
        Path("frontend/pages").rglob("*.ts")
    )
    for path in page_files:
        rel = str(path.relative_to("frontend/pages"))
        if rel.startswith("api/"):
            continue
        # infer route path from filename (rough but fine for MVP)
        route = (
            "/" + rel.replace("index.tsx", "")
            .replace("index.ts", "")
            .replace(".tsx", "")
            .replace(".ts", "")
        )
        route = route.replace("\\", "/")
        if route.endswith("/"):
            route = route[:-1]
        if not route:
            route = "/"
        paths.append(route or "/")
    if "/browser" not in paths:
        paths.append("/browser")
    return sorted(set(paths))


# ---------- Manifest ----------
def load_manifest() -> Dict[str, Any]:
    if MANIFEST_PATH.exists():
        try:
            return json.loads(MANIFEST_PATH.read_text())
        except Exception:
            pass
    return {"probes": []}


def save_manifest(manifest: Dict[str, Any]) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))


def expand_manifest(manifest: Dict[str, Any]) -> Dict[str, Any]:
    probes: List[Dict[str, Any]] = list(manifest.get("probes", []))

    routes = detect_api_routes_runtime() or detect_api_routes_static()
    for route in routes:
        rule = route.get("rule", "")
        if not rule.startswith("/api/"):
            continue
        full_url = f"{API_BASE}{rule}"
        if not any(
            probe
            for probe in probes
            if probe.get("type") == "http"
            and probe.get("method", "GET") == "GET"
            and probe.get("url") == full_url
        ):
            probes.append(
                {"label": f"GET {rule}", "type": "http", "method": "GET", "url": full_url, "expect": 200}
            )
        if rule.endswith("/search") and not any(
            probe
            for probe in probes
            if probe.get("type") == "http"
            and probe.get("url") == full_url
            and probe.get("params")
        ):
            probes.append(
                {
                    "label": "Search hello-world",
                    "type": "http",
                    "method": "GET",
                    "url": full_url,
                    "params": {"q": "hello-world"},
                    "expect": 200,
                }
            )

    for path, label in [
        ("/api/discovery/events", "Discovery stream"),
        ("/api/progress/stream", "Progress stream"),
    ]:
        full_url = f"{API_BASE}{path}"
        if not any(
            probe
            for probe in probes
            if probe.get("type") == "sse" and probe.get("url") == full_url
        ):
            probes.append(
                {"label": label, "type": "sse", "url": full_url, "idle_ok": True, "seconds": 5}
            )

    for route in detect_web_routes()[:10]:
        full_url = f"{RENDERER}{route if route.startswith('/') else '/' + route}"
        if not any(
            probe
            for probe in probes
            if probe.get("type") == "web" and probe.get("url") == full_url
        ):
            probes.append({"label": f"Page {route}", "type": "web", "url": full_url})
    asset_url = f"{RENDERER}/_next/static/chunks/webpack.js"
    if not any(
        probe
        for probe in probes
        if probe.get("type") == "http" and probe.get("url") == asset_url
    ):
        probes.append(
            {
                "label": "Renderer asset: webpack.js",
                "type": "http",
                "method": "GET",
                "url": asset_url,
                "expect": 200,
            }
        )

    manifest["probes"] = probes
    return manifest


# ---------- Runners ----------
def run_http(probe: Dict[str, Any]) -> Dict[str, Any]:
    method = probe.get("method", "GET").upper()
    url = probe["url"]
    expect = int(probe.get("expect", 200))
    params = probe.get("params") or None
    data = probe.get("data") or None
    start = time.time()
    resp = _get(url, params=params) if method == "GET" else _post(url, json=data)
    elapsed = int((time.time() - start) * 1000)
    result = {
        "status": "ok" if resp.status_code == expect else "error",
        "code": resp.status_code,
        "ms": elapsed,
    }
    try:
        result["body_preview"] = (resp.text or "")[:200]
    except Exception:
        pass
    return result


def run_sse(probe: Dict[str, Any]) -> Dict[str, Any]:
    url = probe["url"]
    seconds = int(probe.get("seconds", 5))
    idle_ok = bool(probe.get("idle_ok", True))
    headers = {"Accept": "text/event-stream"}
    try:
        resp = _get(url, headers=headers, timeout=(5, seconds))
    except requests.exceptions.ReadTimeout:
        return {"status": "ok_no_events"} if idle_ok else {"status": "error", "error": "timeout"}
    except requests.exceptions.RequestException as exc:
        return {"status": "error", "error": repr(exc)}
    if resp.status_code != 200:
        if resp.status_code == 404:
            return {"status": "skipped", "code": resp.status_code, "reason": "not_found"}
        return {"status": "error", "code": resp.status_code}
    first: Optional[str] = None
    start = time.time()
    try:
        for line in resp.iter_lines(decode_unicode=True):
            if time.time() - start > seconds:
                break
            if not line or line.startswith(":"):
                continue
            if line.startswith("data:"):
                payload = line[5:].strip()
                if payload:
                    first = payload[:200]
                    break
    except requests.exceptions.ReadTimeout:
        return {"status": "ok_no_events"} if idle_ok else {"status": "error", "error": "timeout"}
    except Exception as exc:
        return {"status": "error", "error": repr(exc)}
    finally:
        try:
            resp.close()
        except Exception:
            pass
    if first:
        return {"status": "ok", "first_event": first}
    return {"status": "ok_no_events"} if idle_ok else {"status": "error", "error": "no events"}


def run_web(probe: Dict[str, Any]) -> Dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        try:
            resp = _get(probe["url"])
            return {"status": "ok" if resp.status_code == 200 else "error", "code": resp.status_code}
        except Exception as exc:
            return {"status": "error", "error": repr(exc)}
    url = probe["url"]
    slug = re.sub(r"[^a-z0-9]+", "_", url.lower())[:40]
    shot = SHOT_DIR / f"page_{slug}.png"

    from playwright.sync_api import sync_playwright  # type: ignore  # re-import to satisfy linters

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.on("console", lambda msg: _write_jsonl(console_path, _console_record(msg)))
        page.on("requestfailed", lambda req: _write_jsonl(net_path, _requestfailed_record(req)))
        try:
            page.goto(url, timeout=60_000)
            page.wait_for_load_state("domcontentloaded", timeout=30_000)
            try:
                from playwright.sync_api import TimeoutError as PlaywrightTimeoutError  # type: ignore
            except Exception:  # pragma: no cover - fallback when playwright not present
                PlaywrightTimeoutError = TimeoutError  # type: ignore
            try:
                page.wait_for_load_state("networkidle", timeout=30_000)
            except PlaywrightTimeoutError:
                log(f"Playwright networkidle timeout for {url}; continuing with screenshot")
            page.screenshot(path=str(shot), full_page=True)
        except Exception as exc:
            browser.close()
            return {"status": "error", "error": repr(exc)}
        browser.close()
    return {"status": "ok", "screenshot": str(shot)}


def run_probe(probe: Dict[str, Any]) -> Dict[str, Any]:
    start = time.time()
    kind = probe.get("type")
    try:
        if kind == "http":
            result = run_http(probe)
        elif kind == "sse":
            result = run_sse(probe)
        elif kind == "web":
            result = run_web(probe)
        else:
            result = {"status": "skipped", "reason": "unknown_type"}
    except Exception as exc:
        result = {"status": "error", "error": repr(exc)}
    result["label"] = probe.get("label")
    result["type"] = kind
    result["url"] = probe.get("url")
    result["ms_total"] = int((time.time() - start) * 1000)
    return result


# ---------- Public API ----------
def run_all() -> Tuple[Dict[str, Any], int]:
    _mkdirs()
    try:
        api_up = _get(f"{API_BASE}/api/meta/health").status_code == 200
    except Exception:
        api_up = False
    if not api_up:
        log("API not detected; starting backend service...")
        _start(API_CMD, LOGS_DIR / "api.log")
        t0 = time.time()
        while time.time() - t0 < 60:
            try:
                if _get(f"{API_BASE}/api/meta/health").status_code == 200:
                    break
            except Exception:
                pass
            time.sleep(0.5)

    try:
        web_up = _get(f"{RENDERER}/api/__meta").status_code == 200
    except Exception:
        web_up = False
    if not web_up:
        log("Renderer not detected; starting web service...")
        _start(WEB_CMD, LOGS_DIR / "web.log", extra_env=WEB_ENV)
        t0 = time.time()
        while time.time() - t0 < 60:
            try:
                if _get(f"{RENDERER}/api/__meta").status_code == 200:
                    break
            except Exception:
                pass
            time.sleep(0.5)

    manifest = expand_manifest(load_manifest())
    save_manifest(manifest)

    steps: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    for probe in manifest.get("probes", []):
        outcome = run_probe(probe)
        steps.append(outcome)
        if outcome.get("status") == "error":
            errors.append(outcome)

    results = {
        "env": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "api_base": API_BASE,
            "renderer": RENDERER,
        },
        "steps": steps,
        "errors": errors,
    }

    (RUN_DIR / "checks.json").write_text(json.dumps(results, indent=2))
    ok_count = sum(1 for step in steps if str(step.get("status", "")).startswith("ok"))
    warn_count = sum(
        1
        for step in steps
        if step.get("status") in {"ok_no_events", "skipped"}
    )
    err_count = len(errors)
    log(f"Probes: {len(steps)}  ✓ok:{ok_count}  ~:{warn_count}  ✗err:{err_count}")
    (RUN_DIR / "summary.md").write_text(
        f"# Diagnostics\n\n- Probes: {len(steps)}\n- OK: {ok_count}\n- ~ (idle/skip): {warn_count}\n- Errors: {err_count}\n"
    )
    return results, (0 if err_count == 0 else 1)


atexit.register(_kill_procs)
